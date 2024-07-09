import taichi as ti

@ti.dataclass
class Node:
    object_id: ti.i32
    parent: ti.i32
    left: ti.i32
    right: ti.i32
    visited: ti.i32
    aabb_min: ti.math.vec3
    aabb_max: ti.math.vec3
    start: ti.i32
    end: ti.i32

@ti.data_oriented
class LBVH:
    def __init__(self, num_leafs):
        self.num_leafs = num_leafs
        self.num_nodes = 2 * self.num_leafs - 1
        # self.leaf_nodes = Node.field(shape=self.num_leafs)
        # self.internal_nodes = Node.field(shape=(self.num_leafs - 1))


        self.nodes = Node.field(shape=self.num_nodes)

        self.sorted_object_ids = ti.field(dtype=ti.i32, shape=self.num_leafs)
        self.object_ids = ti.field(dtype=ti.i32, shape=self.num_leafs)
        self.object_ids_temp = ti.field(dtype=ti.i32, shape=self.num_leafs)

        self.sorted_morton_codes = ti.field(dtype=ti.i32, shape=self.num_leafs)
        self.morton_codes = ti.field(dtype=ti.int32, shape=self.num_leafs)
        self.morton_codes_temp = ti.field(dtype=ti.int32, shape=self.num_leafs)

        self.test = 1
        self.aabb_x = ti.Vector.field(n=3, dtype=ti.f32, shape=8 * self.test)
        self.aabb_x0 = ti.Vector.field(n=3, dtype=ti.f32, shape=8)


        self.aabb_indices = ti.field(dtype=ti.uint32, shape=24 * self.test)

        self.aabb_index0 = ti.field(dtype=ti.uint32, shape=24)
        # self.aabb_index1 = ti.field(dtype=ti.uint32, shape=24)

        self.face_centers = ti.Vector.field(n=3, dtype=ti.f32, shape=self.num_leafs)
        self.zSort_line_idx = ti.field(dtype=ti.uint32, shape=self.num_nodes)
        self.parent_ids = ti.field(dtype=ti.i32, shape=self.num_leafs)

        self.BITS_PER_PASS = 8
        self.RADIX = pow(2, self.BITS_PER_PASS)
        self.passes = (30 + self.BITS_PER_PASS - 1) // self.BITS_PER_PASS
        self.prefix_sum_executer = ti.algorithms.PrefixSumExecutor(self.RADIX)
        self.prefix_sum = ti.field(dtype=ti.i32, shape=self.RADIX)
        self.prefix_sum_temp = ti.field(dtype=ti.i32, shape=self.RADIX)

        self.atomic_flag = ti.field(dtype=ti.i32, shape=self.num_leafs)


    # Expands a 10-bit integer into 30 bits by inserting 2 zeros after each bit.
    @ti.func
    def expand_bits(self, v):
        v = (v | (v << 16)) & 0x030000FF
        v = (v | (v << 8)) & 0x0300F00F
        v = (v | (v << 4)) & 0x030C30C3
        v = (v | (v << 2)) & 0x09249249
        return v

    @ti.func
    def morton_3d(self, x, y, z):
        x = ti.math.clamp(x * 1024., 0., 1023.)
        y = ti.math.clamp(y * 1024., 0., 1023.)
        z = ti.math.clamp(z * 1024., 0., 1023.)
        xx = self.expand_bits(ti.cast(x, ti.uint64))
        yy = self.expand_bits(ti.cast(y, ti.uint64))
        zz = self.expand_bits(ti.cast(z, ti.uint64))
        return ti.cast(xx | (yy << 1) | (zz << 2), ti.int32)

    @ti.kernel
    def assign_morton(self, mesh: ti.template(), aabb_min: ti.math.vec3, aabb_max: ti.math.vec3):

        # max_value = -1
        # min0 = ti.math.vec3(1e4)
        # max0 = ti.math.vec3(-1e4)

        for f in mesh.faces:
        # // obtain center of triangle
            u = f.verts[0]
            v = f.verts[1]
            w = f.verts[2]
            pos = (1. / 3.) * (u.x + v.x + w.x)

            pos = 0.5 * (f.aabb_max + f.aabb_min)

            # if f.id < 10:
            #     print(pos[1])
            # pos[1] = 0.0
            # pos = ti.math.vec3(x, y, z)
            self.face_centers[f.id] = pos
            #
            # ti.atomic_max(max0, pos)
            # ti.atomic_min(min0, pos)

        for f in mesh.faces:
            pos = self.face_centers[f.id]
                # = 0.5 * (f.aabb_min + f.aabb_max)
        # // normalize position
            x = (pos[0] - aabb_min[0]) / (aabb_max[0] - aabb_min[0])
            y = (pos[1] - aabb_min[1]) / (aabb_max[1] - aabb_min[1])
            z = (pos[2] - aabb_min[2]) / (aabb_max[2] - aabb_min[2])
        # // clamp to deal with numeric issues
            x = ti.math.clamp(x, 0., 1.)
            y = ti.math.clamp(y, 0., 1.)
            z = ti.math.clamp(z, 0., 1.)

    # // obtain and set morton code based on normalized position
            morton3d = self.morton_3d(x, y, z)
            self.morton_codes[f.id] = morton3d
            # ti.atomic_max(max_value, morton3d)
            self.object_ids[f.id] = f.id

        # return max_value

    @ti.kernel
    def assign_leaf_nodes(self, mesh: ti.template()):
        # print(self.num_leafs)
        for f in mesh.faces:
            # // no need to set parent to nullptr, each child will have a parents
            id = self.object_ids[f.id]
            self.nodes[f.id + self.num_leafs - 1].object_id = id
            self.nodes[f.id + self.num_leafs - 1].left = -1
            self.nodes[f.id + self.num_leafs - 1].right = -1
            self.nodes[f.id + self.num_leafs - 1].aabb_min = mesh.faces.aabb_min[id]
            self.nodes[f.id + self.num_leafs - 1].aabb_max = mesh.faces.aabb_max[id]

            # // need to set for internal node parent to nullptr, for testing later
            # // there is one less internal node than leaf node, test for that
            # self.internal_nodes[i].parent = None

    @ti.func
    def delta(self, i, j):
        ret = -1
        if j <= (self.num_leafs - 1) and j >= 0:
            xor = self.morton_codes[i] ^ self.morton_codes[j]
            if xor == 0:
                ret = 32
            else:
                ret = ti.math.clz(xor)
        return ret

    @ti.func
    def find_split(self, l, r):
        first_code = self.morton_codes[l]
        last_code = self.morton_codes[r]

        ret = -1
        if first_code == last_code:
            ret = (l + r) // 2

        else:
            common_prefix = ti.math.clz(first_code ^ last_code)

            split = l
            step = r - l

            while step > 1:
                step = (step + 1) // 2
                new_split = split + step

                if new_split < r:
                    split_code = self.morton_codes[new_split]
                    split_prefix = ti.math.clz(first_code ^ split_code)
                    if split_prefix > common_prefix:
                        split = new_split

            ret = split
        return ret


    @ti.func
    def determine_range(self, i, n):

        delta_l = self.delta(i, i - 1)
        delta_r = self.delta(i, i + 1)

        d = 1

        delta_min = delta_l
        if delta_r < delta_l:
            d = - 1
            delta_min = delta_r

        # print(d)

        l_max = 2
        while self.delta(i, i + l_max * d) > delta_min:
            l_max <<= 2

        l = 0
        t = l_max // 2
        while t >= 1:
            if i + (l + t) * d >= 0 and i + (l + t) * d < n and self.delta(i, i + (l + t) * d) > delta_min:
                l += t
            t //= 2

        start = i
        end = i + l * d
        if d == -1:
            start = i + l * d
            end = i


        return start, end



    @ti.kernel
    def assign_internal_nodes(self):

        # ti.loop_config(block_dim=64)
        for i in range(self.num_leafs - 1):
            start, end = self.determine_range(i, self.num_leafs)
            split = self.find_split(start, end)
            left = split + self.num_leafs - 1 if split == start else split
            right = split + 1 + self.num_leafs - 1 if split + 1 == end else split + 1
            self.nodes[i].left = left
            self.nodes[i].right = right
            self.nodes[i].visited = 0
            self.nodes[left].parent = i
            self.nodes[right].parent = i
            self.nodes[i].start = start
            self.nodes[i].end = end

        # for i in range(self.num_leafs - 1):
        #     print(i, self.nodes[i].parent)


    @ti.func
    def atomicCAS(self, id, old, new):

        old_value = self.nodes[id].visited
        if self.nodes[id].visited == old:
            self.nodes[id].visited = new

        return old_value

    @ti.kernel
    def init_flag(self):
        for i in range(self.num_leafs):
            parent = self.nodes[i + self.num_leafs - 1].parent
            self.nodes[parent].visited += 1

    def compute_bvh_aabbs(self):

        self.init_flag()
        while True:
            cnt = self.compute_node_aabbs()
            # print("cnt: ", cnt)
            if cnt == 0:
                break
    @ti.kernel
    def compute_node_aabbs(self) -> ti.int32:
        # ti.loop_config(block_dim=64)
        cnt = 0
        for i in range(self.num_leafs - 1):
            if self.nodes[i].visited == 2:
                left, right = self.nodes[i].left, self.nodes[i].right
                min0, min1 = self.nodes[left].aabb_min, self.nodes[right].aabb_min
                max0, max1 = self.nodes[left].aabb_max, self.nodes[right].aabb_max
                self.nodes[i].aabb_min = ti.min(min0, min1)
                self.nodes[i].aabb_max = ti.max(max0, max1)
                parent = self.nodes[i].parent
                self.nodes[i].visited += 1
                self.nodes[parent].visited += 1
                ti.atomic_add(cnt, 1)

        return cnt
        # # id0 = 0 + self.num_leafs - 1
        # cnt = 0
        # cnt_total = 0
        # for i in range(self.num_leafs):
        #     min0, max0 = self.nodes[i + self.num_leafs - 1].aabb_min, self.nodes[i + self.num_leafs - 1].aabb_max
        #     for j in range(self.num_leafs):
        #         min1, max1 = self.nodes[j + self.num_leafs - 1].aabb_min, self.nodes[j + self.num_leafs - 1].aabb_max
        #         ti.atomic_add(cnt_total, 1)
        #         if self.aabb_overlap(min0, max0, min1, max1):
        #             ti.atomic_add(cnt, 1)
        # print(cnt_total / self.num_leafs)
        # #
        cnt = 0
        # # # # for i in range(self.num_leafs):
        # # # i = 0 + self.num_leafs - 1
        # cnt_total = 0
        # for i in range(self.num_leafs):
        # # i = 0
        # # if self.num_leafs >= 2400:
        # #     i = 5184 + self.num_leafs - 1
        #     min0, max0 = self.nodes[i + self.num_leafs - 1].aabb_min, self.nodes[i + self.num_leafs - 1].aabb_max
        #     # # print(min0, max0)
        #
        #     stack_size = 1024
        #     stack = ti.Vector([-1 for j in range(128)])
        #     stack[0] = 0
        #     stack_counter = 1
        #
        #     while stack_counter > 0:
        #
        #         if stack_counter >= 1024 - 1:
        #             # print(i, "fuck\n")
        #             break
        #
        #         stack_counter -= 1
        #         idx = stack[stack_counter]
        #         stack[stack_counter] = -1
        #         min1, max1 = self.nodes[idx].aabb_min, self.nodes[idx].aabb_max
        #         if self.aabb_overlap(min0, max0, min1, max1):
        #             ti.atomic_add(cnt_total, 1)
        #             if idx >= self.num_leafs - 1:
        #                 ti.atomic_add(cnt, 1)
        #
        #             else:
        #                 left, right = self.nodes[idx].left, self.nodes[idx].right
        #                 stack[stack_counter] = left
        #                 stack_counter += 1
        #                 stack[stack_counter] = right
        #                 stack_counter += 1
        #
        #     # print(stack)
        # print(cnt_total /self.num_leafs)


    @ti.kernel
    def count_frequency(self, pass_num: ti.i32):
        for i in range(self.num_leafs):
            digit = (self.morton_codes[i] >> (pass_num * self.BITS_PER_PASS)) & (self.RADIX - 1)
            ti.atomic_add(self.prefix_sum[digit], 1)


    @ti.kernel
    def sort_by_digit(self, pass_num: ti.i32):

        for i in range(self.num_leafs):
            I = self.num_leafs - 1 - i
            digit = (self.morton_codes[I] >> (pass_num * self.BITS_PER_PASS)) & (self.RADIX - 1)
            idx = ti.atomic_sub(self.prefix_sum[digit], 1) - 1
            if idx >= 0:
                self.sorted_object_ids[idx] = self.object_ids[I]
                self.sorted_morton_codes[idx] = self.morton_codes[I]

    @ti.kernel
    def upsweep(self, step: ti.int32, size: ti.int32):
        offset = step - 1
        for i in range(size):
            id = offset + step * i
            self.prefix_sum[id] += self.prefix_sum[id - (step >> 1)]

    @ti.kernel
    def downsweep(self, step: ti.int32, size: ti.int32):
        offset = step - 1
        offset_rev = (step >> 1)
        for i in range(size):
            id = offset + step * i
            temp = self.prefix_sum[id - offset_rev]
            self.prefix_sum[id - offset_rev] = self.prefix_sum[id]
            self.prefix_sum[id] += temp


    @ti.kernel
    def add_count(self):

        for i in range(self.RADIX):
            self.prefix_sum[i] += self.prefix_sum_temp[i]

    def blelloch_scan(self):

        self.prefix_sum_temp.copy_from(self.prefix_sum)

        d = 0
        test = self.RADIX
        while test > 1:
            step = 1 << (d + 1)
            size = self.RADIX // step
            self.upsweep(step, size)

            d += 1
            test //= 2

        self.prefix_sum[self.RADIX - 1] = 0
        d = self.BITS_PER_PASS - 1

        while d >= 0:
            step = 1 << (d + 1)
            size = self.RADIX // step
            self.downsweep(step, size)
            d -= 1

        self.add_count()

    def radix_sort(self):
        # print(passes)
        for pi in range(self.passes):
            self.prefix_sum.fill(0)
            self.count_frequency(pi)
            self.prefix_sum_executer.run(self.prefix_sum)
            # self.blelloch_scan()
            self.sort_by_digit(pi)
            self.morton_codes.copy_from(self.sorted_morton_codes)
            self.object_ids.copy_from(self.sorted_object_ids)

    def sort(self):
        ti.algorithms.parallel_sort(keys=self.morton_codes, values=self.object_ids)

    def build(self, mesh, aabb_min_g, aabb_max_g):

        # for i in range(2):
        self.nodes.visited.fill(0)
        self.nodes.parent.fill(-1)
        # self.nodes.visited.fill(0)
        self.assign_morton(mesh, aabb_min_g, aabb_max_g)
        # self.radix_sort()

        self.sort()
        # self.sort()
        # ti.algorithms.parallel_sort(keys=self.morton_codes, values=self.object_ids)

        self.assign_leaf_nodes(mesh)
        self.assign_internal_nodes()
        self.compute_bvh_aabbs()

    @ti.func
    def aabb_overlap(self, min1, max1, min2, max2):
        return (min1[0] <= max2[0] and max1[0] >= min2[0] and
                min1[1] <= max2[1] and max1[1] >= min2[1] and
                min1[2] <= max2[2] and max1[2] >= min2[2])


    @ti.func
    def traverse_bvh_single(self, min0, max0, i, cache, nums):

        stack = ti.Vector([-1 for j in range(8)])
        stack[0] = 0
        stack_counter = 1
        idx = 0
        cnt = 0
        while stack_counter > 0:
            # print(stack)
            stack_counter -= 1
            idx = stack[stack_counter]
            min1, max1 = self.nodes[idx].aabb_min, self.nodes[idx].aabb_max
            # print(min1, max1)
            cnt += 1
            if self.aabb_overlap(min0, max0, min1, max1):
                if idx >= self.num_leafs - 1:
                    cache[i, nums[i]] = self.nodes[idx].object_id
                    nums[i] += 1
                    ti.atomic_add(cnt, 1)

                else:
                    left, right = self.nodes[idx].left, self.nodes[idx].right
                    stack[stack_counter] = left
                    stack_counter += 1
                    stack[stack_counter] = right
                    stack_counter += 1

        return cnt

    @ti.func
    def traverse_bvh_single_dy(self, min0, max0, i, cache, nums):

        stack = ti.Vector([-1 for j in range(128)])
        stack[0] = 0
        stack_counter = 1
        idx = 0
        cnt = 0
        while stack_counter > 0:
            # stack_counter = ti.math.clamp(stack_counter, 0, 127)
            # if stack_counter >= 127:
            #     break
            stack_counter -= 1
            idx = stack[stack_counter]
            min1, max1 = self.nodes[idx].aabb_min, self.nodes[idx].aabb_max
            cnt += 1
            if self.aabb_overlap(min0, max0, min1, max1):
                if idx >= self.num_leafs - 1:
                    cache[i, nums[i]] = self.nodes[idx].object_id
                    nums[i] += 1
                    ti.atomic_add(cnt, 1)

                else:
                    left, right = self.nodes[idx].left, self.nodes[idx].right
                    if stack_counter < 126:
                        stack[stack_counter] = left
                        stack_counter += 1

                    if stack_counter < 126:
                        stack[stack_counter] = left
                        stack_counter += 1
        #
        return cnt

    @ti.kernel
    def update_zSort_face_centers_and_line(self):

        for i in range(self.num_leafs - 1):
            self.zSort_line_idx[2 * i + 0] = self.object_ids[i]
            self.zSort_line_idx[2 * i + 1] = self.object_ids[i + 1]

    def draw_zSort(self, scene):
        self.update_zSort_face_centers_and_line()
        scene.lines(self.face_centers, indices=self.zSort_line_idx, width=1.0, color=(1, 0, 0))
    #
    @ti.kernel
    def update_aabb_x_and_lines(self):
        for n in range(self.test):
            # i = n + self.num_leafs - 1
            aabb_min = self.nodes[n].aabb_min
            aabb_max = self.nodes[n].aabb_max

            self.aabb_x[8 * n + 0] = ti.math.vec3(aabb_max[0], aabb_max[1], aabb_max[2])
            self.aabb_x[8 * n + 1] = ti.math.vec3(aabb_min[0], aabb_max[1], aabb_max[2])
            self.aabb_x[8 * n + 2] = ti.math.vec3(aabb_min[0], aabb_max[1], aabb_min[2])
            self.aabb_x[8 * n + 3] = ti.math.vec3(aabb_max[0], aabb_max[1], aabb_min[2])

            self.aabb_x[8 * n + 4] = ti.math.vec3(aabb_max[0], aabb_min[1], aabb_max[2])
            self.aabb_x[8 * n + 5] = ti.math.vec3(aabb_min[0], aabb_min[1], aabb_max[2])
            self.aabb_x[8 * n + 6] = ti.math.vec3(aabb_min[0], aabb_min[1], aabb_min[2])
            self.aabb_x[8 * n + 7] = ti.math.vec3(aabb_max[0], aabb_min[1], aabb_min[2])

            self.aabb_indices[24 * n + 0] = 8 * n + 0
            self.aabb_indices[24 * n + 1] = 8 * n + 1
            self.aabb_indices[24 * n + 2] = 8 * n + 1
            self.aabb_indices[24 * n + 3] = 8 * n + 2
            self.aabb_indices[24 * n + 4] = 8 * n + 2
            self.aabb_indices[24 * n + 5] = 8 * n + 3
            self.aabb_indices[24 * n + 6] = 8 * n + 3
            self.aabb_indices[24 * n + 7] = 8 * n + 0
            self.aabb_indices[24 * n + 8] = 8 * n + 4
            self.aabb_indices[24 * n + 9] = 8 * n + 5
            self.aabb_indices[24 * n + 10] = 8 * n + 5
            self.aabb_indices[24 * n + 11] = 8 * n + 6
            self.aabb_indices[24 * n + 12] = 8 * n + 6
            self.aabb_indices[24 * n + 13] = 8 * n + 7
            self.aabb_indices[24 * n + 14] = 8 * n + 7
            self.aabb_indices[24 * n + 15] = 8 * n + 4
            self.aabb_indices[24 * n + 16] = 8 * n + 0
            self.aabb_indices[24 * n + 17] = 8 * n + 4
            self.aabb_indices[24 * n + 18] = 8 * n + 1
            self.aabb_indices[24 * n + 19] = 8 * n + 5
            self.aabb_indices[24 * n + 20] = 8 * n + 2
            self.aabb_indices[24 * n + 21] = 8 * n + 6
            self.aabb_indices[24 * n + 22] = 8 * n + 3
            self.aabb_indices[24 * n + 23] = 8 * n + 7

    @ti.kernel
    def update_aabb_x_and_line0(self, n: ti.i32):

        aabb_min = self.nodes[n].aabb_min
        aabb_max = self.nodes[n].aabb_max

        # print(aabb_min, aabb_max)

        self.aabb_x0[0] = ti.math.vec3(aabb_max[0], aabb_max[1], aabb_max[2])
        self.aabb_x0[1] = ti.math.vec3(aabb_min[0], aabb_max[1], aabb_max[2])
        self.aabb_x0[2] = ti.math.vec3(aabb_min[0], aabb_max[1], aabb_min[2])
        self.aabb_x0[3] = ti.math.vec3(aabb_max[0], aabb_max[1], aabb_min[2])

        self.aabb_x0[4] = ti.math.vec3(aabb_max[0], aabb_min[1], aabb_max[2])
        self.aabb_x0[5] = ti.math.vec3(aabb_min[0], aabb_min[1], aabb_max[2])
        self.aabb_x0[6] = ti.math.vec3(aabb_min[0], aabb_min[1], aabb_min[2])
        self.aabb_x0[7] = ti.math.vec3(aabb_max[0], aabb_min[1], aabb_min[2])

        self.aabb_index0[0] = 0
        self.aabb_index0[1] = 1
        self.aabb_index0[2] = 1
        self.aabb_index0[3] = 2
        self.aabb_index0[4] = 2
        self.aabb_index0[5] = 3
        self.aabb_index0[6] = 3
        self.aabb_index0[7] = 0
        self.aabb_index0[8] = 4
        self.aabb_index0[9] = 5
        self.aabb_index0[10] = 5
        self.aabb_index0[11] = 6
        self.aabb_index0[12] = 6
        self.aabb_index0[13] = 7
        self.aabb_index0[14] = 7
        self.aabb_index0[15] = 4
        self.aabb_index0[16] = 0
        self.aabb_index0[17] = 4
        self.aabb_index0[18] = 1
        self.aabb_index0[19] = 5
        self.aabb_index0[20] = 2
        self.aabb_index0[21] = 6
        self.aabb_index0[22] = 3
        self.aabb_index0[23] = 7


    def draw_bvh_aabb(self, scene):
        self.update_aabb_x_and_lines()
        scene.lines(self.aabb_x, indices=self.aabb_indices, width=2.0, color=(0, 0, 0))

    def draw_bvh_aabb_test(self, scene, n_leaf, n_internal):
        n_leaf += (self.num_leafs - 1)
        self.update_aabb_x_and_line0(n_leaf)
        scene.lines(self.aabb_x0, indices=self.aabb_index0, width=2.0, color=(0, 1, 0))
        # pos = self.face_centers[n_leaf]
        # scene.particles(, indices=self.aabb_index0, width=2.0, color=(0, 1, 0))

        self.update_aabb_x_and_line0(n_internal)
        scene.lines(self.aabb_x0, indices=self.aabb_index0, width=2.0, color=(0, 0, 1))