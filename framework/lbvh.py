import taichi as ti

@ti.dataclass
class Node:
    object_id: ti.i32
    parent: ti.i32
    child_a: ti.i32
    child_b: ti.i32
    visited: ti.i32
    aabb_min: ti.math.vec3
    aabb_max: ti.math.vec3

@ti.data_oriented
class LBVH:
    def __init__(self, num_leafs):
        self.num_leafs = num_leafs
        self.leaf_nodes = Node.field(shape=self.num_leafs)
        self.internal_nodes = Node.field(shape=(self.num_leafs - 1))

        self.sorted_object_ids = ti.field(dtype=ti.i32, shape=self.num_leafs)
        self.object_ids = ti.field(dtype=ti.i32, shape=self.num_leafs)

        self.sorted_morton_codes = ti.field(dtype=ti.i32, shape=self.num_leafs)
        self.morton_codes = ti.field(dtype=ti.uint64, shape=self.num_leafs)

        self.aabb_x = ti.Vector.field(n=3, dtype=ti.f32, shape=8 * (2 * self.num_leafs - 1))
        self.aabb_indices = ti.field(dtype=ti.uint32, shape=12 * (2 * self.num_leafs - 1))

        self.face_centers = ti.Vector.field(n=3, dtype=ti.f32, shape=self.num_leafs)
        self.zSort_line_idx = ti.field(dtype=ti.uint32, shape=2 * (self.num_leafs - 1))

    # Expands a 10-bit integer into 30 bits by inserting 2 zeros after each bit.
    @ti.func
    def expand_bits(self, v):
        v = (v * ti.uint64(0x00010001)) & ti.uint64(0xFF0000FF)
        v = (v * ti.uint64(0x00000101)) & ti.uint64(0x0F00F00F)
        v = (v * ti.uint64(0x00000011)) & ti.uint64(0xC30C30C3)
        v = (v * ti.uint64(0x00000005)) & ti.uint64(0x49249249)
        return v

    @ti.func
    def morton_3d(self, x, y, z):
        x = ti.math.clamp(x * 1024., 0., 1023.)
        y = ti.math.clamp(y * 1024., 0., 1023.)
        z = ti.math.clamp(z * 1024., 0., 1023.)
        xx = self.expand_bits(ti.cast(x, ti.uint64))
        yy = self.expand_bits(ti.cast(y, ti.uint64))
        zz = self.expand_bits(ti.cast(z, ti.uint64))
        return xx * 4 + yy * 2 + zz

    @ti.kernel
    def assign_morton(self, mesh: ti.template(), aabb_min: ti.math.vec3, aabb_max: ti.math.vec3):

        for f in mesh.faces:
        # // obtain center of triangle
            u = f.verts[0]
            v = f.verts[1]
            w = f.verts[2]
            pos = (1. / 3.) * (u.x + v.x + w.x)
            self.face_centers[f.id] = pos

        # // normalize position
            x = (pos[0] - aabb_min[0]) / (aabb_max[0] - aabb_min[0])
            y = (pos[1] - aabb_min[1]) / (aabb_max[1] - aabb_min[1])
            z = (pos[2] - aabb_min[2]) / (aabb_max[2] - aabb_min[2])
        # // clamp to deal with numeric issues
            x = ti.math.clamp(x, 0., 1.)
            y = ti.math.clamp(y, 0., 1.)
            z = ti.math.clamp(z, 0., 1.)

    # // obtain and set morton code based on normalized position
            self.morton_codes[f.id] = self.morton_3d(x, y, z)
            self.object_ids[f.id] = f.id

    @ti.kernel
    def assign_leaf_nodes(self):
        for i in range(self.num_leafs):
            # // no need to set parent to nullptr, each child will have a parent
            self.leaf_nodes[i].object_id = self.sorted_object_ids[i]
            # // needed to recognize that this node is a leaf
            self.leaf_nodes[i].child_a = -1
            self.leaf_nodes[i].child_b = -1

            # // need to set for internal node parent to nullptr, for testing later
            # // there is one less internal node than leaf node, test for that
            # self.internal_nodes[i].parent = None

    @ti.func
    def delta(self, a, b, n, ka):
        # // this guard is for leaf nodes, not internal nodes (hence [0, n-1])
        if (b < 0) or (b > n - 1):
            return -1
        kb = self.sorted_morton_codes[b]
        if ka == kb:
            # // if keys are equal, use id as fallback
            # // (+32 because they have the same morton code)
            return 32 + ti.math.clz(ti.cast(a, ti.uint32) ^ ti.cast(b, ti.uint32))
        # // clz = count leading zeros
        return ti.math.clz(ka ^ kb)

    @ti.func
    def find_split(self, first, last, n):
        first_code = self.sorted_morton_codes[first]

        # calculate the number of highest bits that are the same
        # for all objects, using the count-leading-zeros intrinsic

        common_prefix = self.delta(first, last, n, first_code)

        # use binary search to find where the next bit differs
        # specifically, we are looking for the highest object that
        # shares more than commonPrefix bits with the first one

        # initial guess
        split = first

        step = last - first

        while step > 1:
            # exponential decrease
            step = (step + 1) >> 1
            # proposed new position
            new_split = split + step

            if new_split < last:
                split_prefix = self.delta(first, new_split, n, first_code)
                if split_prefix > common_prefix:
                    # accept proposal
                    split = new_split

        return split

    @ti.func
    def determine_range(self, n, i) -> ti.math.ivec2:
        ki = self.sorted_morton_codes[i]  # key of i

        # determine direction of the range(+1 or -1)

        delta_l = self.delta(i, i - 1, n, ki)
        delta_r = self.delta(i, i + 1, n, ki)

        d = 0  # direction

        # min of delta_r and delta_l
        delta_min = 0
        if delta_r < delta_l:
            d = -1
            delta_min = delta_r
        else:
            d = 1
            delta_min = delta_l

        # compute upper bound of the length of the range
        l_max = 2
        while self.delta(i, i + l_max * d, n, ki) > delta_min:
            l_max <<= 1

        # find other end using binary search
        l = 0
        t = l_max >> 1
        while t > 0:
            if self.delta(i, i + (l + t) * d, n, ki) > delta_min:
                l += t
            t >>= 1

        j = i + l * d

        # // ensure i <= j
        ret = ti.math.ivec2(0)
        if i < j:
            ret = ti.math.ivec2([i, j])
        else:
            ret = ti.math.ivec2([j, i])
        return ret

    @ti.kernel
    def assign_internal_nodes(self):
        for i in range(self.num_leafs - 1):
            # find out which range of objects the node corresponds to
            range1 = self.determine_range(self.num_leafs, i)
            # // determine where to split the range
            split = self.find_split(range1.x, range1.y, self.num_leafs)

            # // select child a
            child_a = None
            if split == range1[0]:
                child_a = self.leaf_nodes[split]
            else:
                child_a = self.internal_nodes[split]

            # select child b
            child_b = None
            if split + 1 == range1[1]:
                child_b = self.leaf_nodes[split + 1]
            else:
                child_b = self.internal_nodes[split + 1]

            # record parent-child relationships
            self.internal_nodes[i].child_a = child_a
            self.internal_nodes[i].child_b = child_b
            self.internal_nodes[i].visited = 0
            self.internal_nodes[child_a].parent = i
            self.internal_nodes[child_b].parent = i

    @ti.kernel
    def set_aabb(self):

        for i in range(self.num_leafs):
            object_id = self.leaf_nodes[i].object_id
            u = self.mesh.faces.verts[0]
            v = self.mesh.faces.verts[1]
            w = self.mesh.faces.verts[2]

            # set bounding box of leaf node
            self.leaf_nodes[i].aabb_min = ti.min(u.x, v.x, w.x)
            self.leaf_nodes[i].aabb_max = ti.max(u.x, v.x, w.x)

            #recursively set tree bounding boxes
            #{current_node} is always an internal node(since it is parent of another)
            current_node = self.leaf_nodes[i].parent
            while True:
                # // we have reached the parent of the root node: terminate
                if current_node == -1:
                    break

                # // we have reached an inner node: check whether the node was visited
                visited = ti.atomic_add(self.internal_nodes[current_node].visited, 1)

                # // this is the first thread entering: terminate
                if visited == 0:
                    break

                # this is the second thread entering, we know that our sibling has
                # reached the current node and terminated,
                # and hence the sibling bounding box is correct

                # set running bounding box to be the union of bounding boxes
                child_a = self.internal_nodes[current_node].child_a
                child_b = self.internal_nodes[current_node].child_b
                self.internal_nodes[current_node].aabb_min = ti.min(self.internal_nodes[child_a].aabb_min, self.internal_nodes[child_b].aabb_min)
                self.internal_nodes[current_node].aabb_max = ti.max(self.internal_nodes[child_a].aabb_max, self.internal_nodes[child_b].aabb_max)
                #  continue traversal
                current_node = self.internal_nodes[current_node].parent

    def build(self, mesh, aabb_min_g, aabb_max_g):
        # self.internal_nodes.parent.fill(-1)
        self.assign_morton(mesh, aabb_min_g, aabb_max_g)
        ti.algorithms.parallel_sort(keys=self.morton_codes, values=self.object_ids)
        # self.assign_leaf_nodes()
        # self.assign_internal_nodes()
        # self.set_aabb()


    @ti.kernel
    def update_zSort_face_centers_and_line(self):

        for i in range(self.num_leafs - 1):
            self.zSort_line_idx[2 * i + 0] = self.object_ids[i]
            self.zSort_line_idx[2 * i + 1] = self.object_ids[i + 1]

    def draw_zSort(self, scene):
        self.update_zSort_face_centers_and_line()
        scene.lines(self.face_centers, indices=self.zSort_line_idx, width=1.0, color=(1, 0, 0))
    #
    # def draw_bvh_aabb(self, scene):
    #     scene.lines(self.aabb_x, indices=self.aabb_indices, width=1.0, color=(0, 0, 0))