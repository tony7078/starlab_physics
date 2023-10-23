import taichi as ti
import meshtaichi_patcher as Patcher

import ccd as ccd
import ipc_utils as cu
import barrier_functions as barrier

@ti.data_oriented
class Solver:
    def __init__(self,
                 my_mesh,
                 static_mesh,
                 bottom,
                 k=1e5,
                 dt=1e-3,
                 max_iter=1000):
        self.my_mesh = my_mesh
        self.static_mesh = static_mesh
        self.k = k
        self.dt = dt
        self.dtSq = dt ** 2
        self.max_iter = max_iter
        self.gravity = -5.81
        self.bottom = bottom
        self.id3 = ti.math.mat3([[1, 0, 0],
                                 [0, 1, 0],
                                 [0, 0, 1]])

        self.verts = self.my_mesh.mesh.verts
        self.num_verts = len(self.my_mesh.mesh.verts)
        self.edges = self.my_mesh.mesh.edges
        self.num_edges = len(self.edges)
        self.faces = self.my_mesh.mesh.faces
        self.num_faces = len(self.my_mesh.mesh.faces)
        self.face_indices = self.my_mesh.face_indices

        self.verts_static = self.static_mesh.mesh.verts
        self.num_verts_static = len(self.static_mesh.mesh.verts)
        self.edges_static = self.static_mesh.mesh.edges
        self.num_edges_static = len(self.edges_static)
        self.faces_static = self.static_mesh.mesh.faces
        self.face_indices_static = self.static_mesh.face_indices
        self.num_faces_static = len(self.static_mesh.mesh.faces)

        self.snode = ti.root.dynamic(ti.i, 1024, chunk_size=32)
        self.candidatesVT = ti.field(ti.math.uvec2)
        self.snode.place(self.candidatesVT)

        self.S = ti.root.dynamic(ti.i, 1024, chunk_size=32)
        self.mmcvid = ti.field(ti.math.ivec2)
        # self.mmcvid_ee = ti.field(ti.math.ivec2)
        self.S.place(self.mmcvid)
        # self.S.place(self.mmcvid_ee)
        self.dHat = 1e-4
        # self.test()
        #
        # self.normals = ti.Vector.field(n=3, dtype = ti.f32, shape = 2 * self.num_faces)
        self.normals_static = ti.Vector.field(n=3, dtype=ti.f32, shape=2 * self.num_faces_static)

        self.radius = 0.01
        self.contact_stiffness = 1e3
        self.damping_factor = 0.001
        self.grid_n = 128
        self.grid_particles_list = ti.field(ti.i32)
        self.grid_block = ti.root.dense(ti.ijk, (self.grid_n, self.grid_n, self.grid_n))
        self.partical_array = self.grid_block.dynamic(ti.l, len(self.my_mesh.mesh.verts))
        self.partical_array.place(self.grid_particles_list)
        self.grid_particles_count = ti.field(ti.i32)
        ti.root.dense(ti.ijk, (self.grid_n, self.grid_n, self.grid_n)).place(self.grid_particles_count)
        self.x_t = ti.Vector.field(n=3, dtype=ti.f32, shape=len(self.verts))


        self.dist_tol = 1e-2

        self.p1 = ti.math.vec3([0., 0., 0.])
        self.p2 = ti.math.vec3([0., 0., 0.])
        self.alpha = ti.math.vec3([0., 0., 0.])

        self.p = ti.Vector.field(n=3, shape=2, dtype=ti.f32)

        self.intersect = ti.Vector.field(n=3, dtype=ti.f32, shape=len(self.verts))



        print(f"verts #: {len(self.my_mesh.mesh.verts)}, elements #: {len(self.my_mesh.mesh.edges)}")
        # self.setRadius()
        # print(f"radius: {self.radius}")
        #
        # print(f'{self.edges.vid}')
        # print(f'{self.edges_static.vid[4]}')
        # self.reset()

        # for PCG
        self.b = ti.Vector.field(3, dtype=ti.f32, shape=self.num_verts)
        self.r = ti.Vector.field(3, dtype=ti.f32, shape=self.num_verts)
        self.p = ti.Vector.field(3, dtype=ti.f32, shape=self.num_verts)
        self.Ap = ti.Vector.field(3, dtype=ti.f32, shape=self.num_verts)
        self.z = ti.Vector.field(3, dtype=ti.f32, shape=self.num_verts)
        self.mul_ans =  ti.Vector.field(3, dtype=ti.f32, shape=self.num_verts)


    def reset(self):
        self.verts.x.copy_from(self.verts.x0)
        self.verts.v.fill(0.0)
    @ti.func
    def aabb_intersect(self, a_min: ti.math.vec3, a_max: ti.math.vec3,
                       b_min: ti.math.vec3, b_max: ti.math.vec3):

        return  a_min[0] <= b_max[0] and \
                a_max[0] >= b_min[0] and \
                a_min[1] <= b_max[1] and \
                a_max[1] >= b_min[1] and \
                a_min[2] <= b_max[2] and \
                a_max[2] >= b_min[2]

    @ti.kernel
    def computeVtemp(self):
        for v in self.verts:
            v.v += (v.f_ext / v.m) * self.dt

    @ti.kernel
    def globalSolveVelocity(self):
        for v in self.verts:
            v.v -= v.g / v.h

    @ti.kernel
    def add(self, ans: ti.template(), a: ti.template(), k: ti.f32, b: ti.template()):
        for i in ans:
            ans[i] = a[i] + k * b[i]

    @ti.kernel
    def dot(self, a: ti.template(), b: ti.template()) -> ti.f32:
        ans = 0.0
        ti.loop_config(block_dim=32)
        for i in a: ans += a[i].dot(b[i])
        return ans

    @ti.kernel
    def computeY(self):
        for v in self.verts:
            v.y = v.x + v.v * self.dt

    @ti.kernel
    def computeNextState(self):
        for v in self.verts:
            v.v = (1.0 - self.damping_factor) * (v.x_k - v.x) / self.dt
            v.x = v.x_k

    @ti.kernel
    def evaluateMomentumConstraint(self):
        for v in self.verts:
            v.g = v.m * (v.x_k - v.y)
            v.h = v.m

    @ti.kernel
    def evaluateSpringConstraint(self):
        for e in self.edges:

            xij = e.verts[0].x_k - e.verts[1].x_k
            coeff = self.dtSq * self.k
            grad = coeff * (xij - e.l0 * xij.normalized(1e-6))

            dir = (e.verts[0].x_k - e.verts[1].x_k).normalized(1e-4)

            # m0, m1 = e.verts[0].m, e.verts[1].m
            # msum = m0 + m1
            # center = (m0 * e.verts[0].x_k + m1 * e.verts[1].x_k) / msum
            # dir = (e.verts[0].x_k - e.verts[1].x_k).normalized(1e-4)
            # l0 = e.l0
            # p0 = center + l0 * (m0 / msum) * dir
            # p1 = center - l0 * (m1 / msum) * dir

            e.verts[0].g += grad
            e.verts[1].g -= grad
            e.verts[0].h += coeff
            e.verts[1].h += coeff

    @ti.kernel
    def compute_search_dir(self):

        for v in self.verts:
            v.dx = -(v.g / v.h)

    @ti.kernel
    def step_forward(self, step_size: ti.f32):
        for v in self.verts:
            v.x_k += step_size * v.dx

    @ti.kernel
    def evaluateCollisionConstraint(self):
        for i in self.mmcvid:
            mi = self.mmcvid[i]
            if mi[0] >= 0:
                print("EE")
                # cu.g_EE()
            else:
                if mi[1] >= 0:
                    vi = -mi[0]-1
                    if mi[2] < 0:
                        cu.g_PP(vi, mi[1])
                        print("PP")
                    elif mi[3] < 0:
                        cu.g_PE()
                        print("PE")
                    else:
                        # cu.g_PT()
                        print("PT")
                else:
                    if mi[2] < 0:
                        # cu.g_PT()
                        print("PT")
                    else:
                        # cu.g_PE()
                        print("PE")


    @ti.kernel
    def computeAABB(self):

        padding_size = 1e-2
        padding = ti.math.vec3([padding_size, padding_size, padding_size])

        for v in self.verts:
            for i in range(3):
                v.aabb_min[i] = ti.min(v.x[i], v.y[i])
                v.aabb_max[i] = ti.max(v.x[i], v.y[i])

            v.aabb_max += padding
            v.aabb_min -= padding


        for f in self.faces_static:

            x0 = f.verts[0].x
            x1 = f.verts[1].x
            x2 = f.verts[2].x

            for i in range(3):
                f.aabb_min[i] = ti.min(x0[i], x1[i], x2[i])
                f.aabb_max[i] = ti.max(x0[i], x1[i], x2[i])

            f.aabb_min -= padding
            f.aabb_max += padding
    @ti.func
    def computeConstraintSet_PT(self, pid: ti.int32, tid: ti.int32):

        v0 = pid
        v1 = self.face_indices_static[3 * tid + 0]
        v2 = self.face_indices_static[3 * tid + 1]
        v3 = self.face_indices_static[3 * tid + 2]


        x0 = self.verts.x_k[v0]
        x1 = self.verts_static.x[v1]   #r
        x2 = self.verts_static.x[v2]   #g
        x3 = self.verts_static.x[v3]   #c

        dtype = cu.d_type_PT(x0, x1, x2, x3)
        if dtype == 0:           #r
            d = cu.d_PP(x0, x1)
            if d < self.dHat:
                g0, g1 = cu.g_PP(x0, x1)

                ld = barrier.compute_g_b(d, self.dHat)
                sch = g0.dot(g0) / self.verts.h[v0]
                ld = (d - self.dHat) / sch

                self.verts.g[v0] += ld * g0
                self.verts.h[v0] += ld
                self.mmcvid.append(ti.math.ivec2([pid, tid]))


        elif dtype == 1:
            d = cu.d_PP(x0, x2)  #g
            if d < self.dHat:
                g0, g2 = cu.g_PP(x0, x2)

                ld = barrier.compute_g_b(d, self.dHat)
                sch = g0.dot(g0) / self.verts.h[v0]
                ld = (d - self.dHat) / sch

                self.verts.g[v0] += ld * g0
                self.verts.h[v0] += ld
                self.mmcvid.append(ti.math.ivec2([pid, tid]))

        elif dtype == 2:
            d = cu.d_PP(x0, x3) #c
            if d < self.dHat:
                g0, g3 = cu.g_PP(x0, x3)

                ld = barrier.compute_g_b(d, self.dHat)
                sch = g0.dot(g0) / self.verts.h[v0]
                ld = (d - self.dHat) / sch

                self.verts.g[v0] += ld * g0
                self.verts.h[v0] += ld
                self.mmcvid.append(ti.math.ivec2([pid, tid]))
              # s

        elif dtype == 3:
            d = cu.d_PE(x0, x1, x2) # r-g
            if d < self.dHat:
                g0, g1, g2 = cu.g_PE(x0, x1, x2)
                ld = barrier.compute_g_b(d, self.dHat)
                sch = g0.dot(g0) / self.verts.h[v0]
                ld = (d - self.dHat) / sch

                self.verts.g[v0] += ld * g0
                self.verts.h[v0] += ld
                self.mmcvid.append(ti.math.ivec2([pid, tid]))

        elif dtype == 4:
            d = cu.d_PE(x0, x2, x3) #g-c
            if d < self.dHat:
                g0, g2, g3 = cu.g_PE(x0, x1, x2)
                ld = barrier.compute_g_b(d, self.dHat)
                sch = g0.dot(g0) / self.verts.h[v0]
                ld = (d - self.dHat) / sch

                self.verts.g[v0] += ld * g0
                self.verts.h[v0] += ld
                self.mmcvid.append(ti.math.ivec2([pid, tid]))

        elif dtype == 5:
            d = cu.d_PE(x0, x3, x1) #c-r
            if d < self.dHat:
                g0, g3, g1 = cu.g_PE(x0, x3, x1)

                ld = barrier.compute_g_b(d, self.dHat)
                sch = g0.dot(g0) / self.verts.h[v0]
                ld = (d - self.dHat) / sch

                self.verts.g[v0] += ld * g0
                self.verts.h[v0] += ld
                self.mmcvid.append(ti.math.ivec2([pid, tid]))

        elif dtype == 6:            # inside triangle
            d = cu.d_PT(x0, x1, x2, x3)
            if d < self.dHat:
                g0, g1, g2, g3 = cu.g_PT(x0, x1, x2, x3)
                ld = barrier.compute_g_b(d, self.dHat)
                sch = g0.dot(g0) / self.verts.h[v0]
                ld = (d - self.dHat) / sch
                self.verts.g[v0] += ld * g0
                self.verts.h[v0] += ld
                self.mmcvid.append(ti.math.ivec2([pid, tid]))


    @ti.func
    def compute_constraint_energy_PT(self, x: ti.template(), pid: ti.int32, tid: ti.int32) -> ti.f32:

        energy = 0.0
        v0 = pid
        v1 = self.face_indices_static[3 * tid + 0]
        v2 = self.face_indices_static[3 * tid + 1]
        v3 = self.face_indices_static[3 * tid + 2]


        x0 = x[v0]
        x1 = self.verts_static.x[v1]   #r
        x2 = self.verts_static.x[v2]   #g
        x3 = self.verts_static.x[v3]   #c

        dtype = cu.d_type_PT(x0, x1, x2, x3)
        if dtype == 0:           #r
            d = cu.d_PP(x0, x1)
            if d < self.dHat:
                g0, g1 = cu.g_PP(x0, x1)

                ld = barrier.compute_g_b(d, self.dHat)
                sch = g0.dot(g0) / self.verts.h[v0]
                ld = (d - self.dHat) / sch
                energy = 0.5 * ld * (d - self.dHat)

        elif dtype == 1:
            d = cu.d_PP(x0, x2)  #g
            if d < self.dHat:
                g0, g2 = cu.g_PP(x0, x2)

                ld = barrier.compute_g_b(d, self.dHat)
                sch = g0.dot(g0) / self.verts.h[v0]
                ld = (d - self.dHat) / sch
                energy = 0.5 * ld * (d - self.dHat)

        elif dtype == 2:
            d = cu.d_PP(x0, x3) #c
            if d < self.dHat:
                g0, g3 = cu.g_PP(x0, x3)

                ld = barrier.compute_g_b(d, self.dHat)
                sch = g0.dot(g0) / self.verts.h[v0]
                ld = (d - self.dHat) / sch
                energy = 0.5 * ld * (d - self.dHat)

        elif dtype == 3:
            d = cu.d_PE(x0, x1, x2) # r-g
            if d < self.dHat:
                g0, g1, g2 = cu.g_PE(x0, x1, x2)
                ld = barrier.compute_g_b(d, self.dHat)
                sch = g0.dot(g0) / self.verts.h[v0]
                ld = (d - self.dHat) / sch
                energy = 0.5 * ld * (d - self.dHat)

        elif dtype == 4:
            d = cu.d_PE(x0, x2, x3) #g-c
            if d < self.dHat:
                g0, g2, g3 = cu.g_PE(x0, x1, x2)
                ld = barrier.compute_g_b(d, self.dHat)
                sch = g0.dot(g0) / self.verts.h[v0]
                ld = (d - self.dHat) / sch
                energy = 0.5 * ld * (d - self.dHat)

        elif dtype == 5:
            d = cu.d_PE(x0, x3, x1) #c-r
            if d < self.dHat:
                g0, g3, g1 = cu.g_PE(x0, x3, x1)

                ld = barrier.compute_g_b(d, self.dHat)
                sch = g0.dot(g0) / self.verts.h[v0]
                ld = (d - self.dHat) / sch
                energy = 0.5 * ld * (d - self.dHat)
        elif dtype == 6:            # inside triangle
            d = cu.d_PT(x0, x1, x2, x3)
            if d < self.dHat:
                g0, g1, g2, g3 = cu.g_PT(x0, x1, x2, x3)
                ld = barrier.compute_g_b(d, self.dHat)
                sch = g0.dot(g0) / self.verts.h[v0]
                ld = (d - self.dHat) / sch
                energy = 0.5 * ld * (d - self.dHat)
        return energy
    @ti.func
    def computeConstraintSet_TP(self, tid: ti.int32, pid: ti.int32):

        v0 = pid
        v1 = self.face_indices[3 * tid + 0]
        v2 = self.face_indices[3 * tid + 1]
        v3 = self.face_indices[3 * tid + 2]

        # print(f'{v0}, {v1}, {v2}, {v3}')

        x0 = self.verts_static.x[v0]
        x1 = self.verts.x_k[v1]   #r
        x2 = self.verts.x_k[v2]   #g
        x3 = self.verts.x_k[v3]   #c

        dtype = cu.d_type_PT(x0, x1, x2, x3)
        if dtype == 0:           #r
            d = cu.d_PP(x0, x1)
            if d < self.dHat:
                g0, g1 = cu.g_PP(x0, x1)
                ld = barrier.compute_g_b(d, self.dHat)
                # sch = g1.dot(g1) / self.verts.h[v1]
                # ld = (d - self.dHat) / sch

                self.verts.g[v1] += ld * g1
                self.verts.h[v1] += ld

                # self.mmcvid.append(ti.math.ivec4([-v1-1, v0, -1, -1]))

        elif dtype == 1:
            d = cu.d_PP(x0, x2)  #g
            if d < self.dHat:
                g0, g2 = cu.g_PP(x0, x2)
                ld = barrier.compute_g_b(d, self.dHat)
                # sch = g2.dot(g2) / self.verts.h[v2]
                # ld = (d - self.dHat) / sch

                self.verts.g[v2] += ld * g2
                self.verts.h[v2] += ld

        elif dtype == 2:
            d = cu.d_PP(x0, x3) #c
            if d < self.dHat:
                g0, g3 = cu.g_PP(x0, x3)
                ld = barrier.compute_g_b(d, self.dHat)
                # sch = g3.dot(g3) / self.verts.h[v3]
                # ld = (d - self.dHat) / sch

                self.verts.g[v3] += ld * g3
                self.verts.h[v3] += ld

        # self.mmcvid.append(ti.math.ivec4([-v3-1, v0, -1, -1]))

        elif dtype == 3:
            d = cu.d_PE(x0, x1, x2) # r-g
            if d < self.dHat:
                g0, g1, g2 = cu.g_PE(x0, x1, x2)
                ld = barrier.compute_g_b(d, self.dHat)
                # sch = g1.dot(g1) / self.verts.h[v1] + g2.dot(g2) / self.verts.h[v2]
                # ld = (d - self.dHat) / sch

                self.verts.g[v1] += ld * g1
                self.verts.g[v2] += ld * g2
                self.verts.h[v1] += ld
                self.verts.h[v2] += ld
                # self.mmcvid.append(ti.math.ivec4([-v1-1, -v2-1, v0, -1]))

        elif dtype == 4:
            d = cu.d_PE(x0, x2, x3) #g-c
            if d < self.dHat:
                g0, g2, g3 = cu.g_PE(x0, x2, x3)
                ld = barrier.compute_g_b(d, self.dHat)
                # sch = g2.dot(g2) / self.verts.h[v2] + g3.dot(g3) / self.verts.h[v3]
                # ld = (d - self.dHat) / sch

                self.verts.g[v2] += ld * g2
                self.verts.g[v3] += ld * g3

                self.verts.h[v2] += ld
                self.verts.h[v3] += ld
                # self.mmcvid.append(ti.math.ivec4([-v2-1, -v3-1, v0, -1]))

        elif dtype == 5:
            d = cu.d_PE(x0, x3, x1) #c-r
            if d < self.dHat:
                g0, g3, g1 = cu.g_PE(x0, x3, x1)
                ld = barrier.compute_g_b(d, self.dHat)
                # sch = g1.dot(g1) / self.verts.h[v2] + g3.dot(g3) / self.verts.h[v3]
                # ld = (d - self.dHat) / sch

                self.verts.g[v1] += ld * g1
                self.verts.g[v3] += ld * g3

                self.verts.h[v1] += ld
                self.verts.h[v3] += ld
                # self.mmcvid.append(ti.math.ivec4([-v3-1, -v1-1, v0, -1]))

        elif dtype == 6:            # inside triangle
            d = cu.d_PT(x0, x1, x2, x3)
            if d < self.dHat:
                g0, g1, g2, g3 = cu.g_PT(x0, x1, x2, x3)
                ld = barrier.compute_g_b(d, self.dHat)
                # sch = g1.dot(g1) / self.verts.h[v1] + g2.dot(g2) / self.verts.h[v2] + g3.dot(g3) / self.verts.h[v3]
                # ld = (d - self.dHat) / sch

                self.verts.g[v1] += ld * g1
                self.verts.g[v2] += ld * g2
                self.verts.g[v3] += ld * g3

                self.verts.h[v1] += ld
                self.verts.h[v2] += ld
                self.verts.h[v3] += ld
                # self.mmcvid.append(ti.math.ivec4([-v1-1, -v2-1, -v3-1, v0]))

    @ti.func
    def computeConstraintSet_EE(self, eid0: ti.int32, eid1: ti.int32):

        v0 = self.edges.vid[eid0][0]
        v1 = self.edges.vid[eid0][1]
        v2 = self.edges_static.vid[eid1][0]
        v3 = self.edges_static.vid[eid1][1]

        x0 = self.verts.x_k[v0]
        x1 = self.verts.x_k[v1]
        x2 = self.verts_static.x[v2]
        x3 = self.verts_static.x[v3]

        d_type = cu.d_type_EE(x0, x1, x2, x3)
        x01 = x1-x0
        x32 = x2-x3
        # print(d_type)
        is_para = False
        if (x01.cross(x32).norm() < 1e-3):
            is_para = True

        if is_para:
            print("para")                                                 
        # print(f'{d_type}, {is_para}')

        if d_type == 0:
            d = cu.d_PP(x0, x2)
            if(d < self.dHat):
                # print(d_type)
                g0, g2 = cu.g_PP(x0, x2)
                sch = g0.dot(g0) / self.verts.h[v0]
                ld = (d - self.dHat) / sch
                # p0 = x0 - step_size * g0

                self.verts.g[v0] += ld * g0
                self.verts.h[v0] += ld

        elif d_type == 1:
            d = cu.d_PP(x0, x3)
            if (d < self.dHat):
                # print(d_type)
                g0, g3 = cu.g_PP(x0, x3)
                sch = g0.dot(g0) / self.verts.h[v0]
                ld = (d - self.dHat) / sch
                # p0 = x0 - step_size * g0

                self.verts.g[v0] += ld * g0
                self.verts.h[v0] += ld

        elif d_type == 2:
            d = cu.d_PE(x0, x2, x3)
            if (d < self.dHat):
                # print(d_type)
                g0, g1, g2 = cu.g_PE(x0, x2, x3)
                sch = g0.dot(g0) / self.verts.h[v0] + g1.dot(g1) / self.verts.h[v1]
                step_size = (d - self.dHat) / sch
                ld = (d - self.dHat) / sch
                # p0 = x0 - step_size * g0

                self.verts.g[v0] += ld * g0
                self.verts.g[v1] += ld * g0
                self.verts.h[v0] += ld
                self.verts.h[v1] += ld

        elif d_type == 3:
            d = cu.d_PP(x1, x2)
            if (d < self.dHat):
                # print(d_type)
                g1, g2 = cu.g_PP(x1, x2)
                sch = g1.dot(g1) / self.verts.h[v1]
                ld = (d - self.dHat) / sch
                # p0 = x0 - step_size * g0

                self.verts.g[v1] += ld * g1
                self.verts.h[v1] += ld

        elif d_type == 4:
            d = cu.d_PP(x1, x3)
            if (d < self.dHat):
                # print(d_type)
                g1, g3 = cu.g_PP(x1, x3)
                sch = g1.dot(g1) / self.verts.h[v1]
                ld = (d - self.dHat) / sch
                # p0 = x0 - step_size * g0

                self.verts.g[v1] += ld * g1
                self.verts.h[v1] += ld

        elif d_type == 5:
            d = cu.d_PE(x1, x2, x3)
            if (d < self.dHat):
                # print(d_type)
                g1, g2, g3 = cu.g_PE(x1, x2, x3)
                sch = g1.dot(g1) / self.verts.h[v1]
                ld = (d - self.dHat) / sch
                # p0 = x0 - step_size * g0

                self.verts.g[v1] += ld * g1
                self.verts.h[v1] += ld

        elif d_type == 6:
            d = cu.d_PE(x2, x0, x1)
            if (d < self.dHat):
                # print(d_type)
                g2, g0, g1 = cu.g_PE(x2, x0, x1)
                sch = g0.dot(g0) / self.verts.h[v0] + g1.dot(g1) / self.verts.h[v1]
                ld = (d - self.dHat) / sch
                # p0 = x0 - step_size * g0

                self.verts.g[v0] += ld * g0
                self.verts.g[v1] += ld * g0
                self.verts.h[v0] += ld
                self.verts.h[v1] += ld

        elif d_type == 7:
            d = cu.d_PE(x3, x0, x1)
            if (d < self.dHat):
                # print(d_type)
                g3, g0, g1 = cu.g_PE(x3, x0, x1)
                sch = g0.dot(g0) / self.verts.h[v0] + g1.dot(g1) / self.verts.h[v1]
                ld = (d - self.dHat) / sch
                # p0 = x0 - step_size * g0

                self.verts.g[v0] += ld * g0
                self.verts.g[v1] += ld * g0
                self.verts.h[v0] += ld
                self.verts.h[v1] += ld

        elif d_type == 8:
            d = cu.d_EE(x0, x1, x2, x3)
            # print(d)
            if (d < self.dHat):
                # print("test")
                g0, g1, g2, g3 = cu.g_EE(x0, x1, x2, x3)
                sch = g0.dot(g0) / self.verts.h[v0] + g1.dot(g1) / self.verts.h[v1]

                # ld = 0
                # if abs(sch) > 1e-6:
                ld = (d - self.dHat) / sch

                self.verts.g[v0] += ld * g0
                self.verts.g[v1] += ld * g1

                self.verts.h[v0] += ld
                self.verts.h[v1] += ld



    @ti.kernel
    def computeConstraintSet(self):

        self.mmcvid.deactivate()
        # self.mmcvid_ee.deactivate()
        # # point - triangle
        # for v in self.verts:
        #     for fid in range(self.num_faces_static):
        #         self.computeConstraintSet_PT(v.id, fid)
        #
        num = self.num_verts * self.num_faces_static
        for i in range(num):
            pid = i // self.num_faces_static
            fid = i % self.num_faces_static
            self.computeConstraintSet_PT(pid, fid)

        num = self.num_faces * self.num_verts_static
        for i in range(num):
            pid = i // self.num_verts_static
            fid = i % self.num_verts_static
            self.computeConstraintSet_TP(fid, pid)
        #
        # # print(self.mmcvid.length())
        # # triangle - point
        # for f in self.faces:
        #     for vid in range(self.num_verts_static):
        #         self.computeConstraintSet_TP(f.id, vid)

        num = self.num_edges * self.num_edges_static
        for i in range(num):
            ei0 = i // self.num_edges_static
            ei1 = i % self.num_edges_static
            self.computeConstraintSet_EE(ei0, ei1)
        # for e in self.edges:
        #     for eid in range(self.num_edges_static):
        #         self.computeConstraintSet_EE(e.id, eid)

    @ti.kernel
    def ccd_alpha(self) -> ti.f32:
        alpha = 1.0
        for i in self.mmcvid:
            tid, fid = self.mmcvid[i][0], self.mmcvid[i][1]
            x0 = self.verts.x_k[tid]
            dx0 = self.verts.dx[tid]

            v1 = self.face_indices_static[3 * tid + 0]
            v2 = self.face_indices_static[3 * tid + 1]
            v3 = self.face_indices_static[3 * tid + 2]

            x1 = self.verts_static.x[v1]
            x2 = self.verts_static.x[v2]
            x3 = self.verts_static.x[v3]

            dx_zero = ti.math.vec3([0.0, 0.0, 0.0])

            alpha_ccd = ccd.point_triangle_ccd(x0, x1, x2, x3, dx0, dx_zero, dx_zero, dx_zero, 0.1, self.dHat, 1.0)
            # print(alpha_ccd)
            if alpha > alpha_ccd:
                alpha = alpha_ccd

        return alpha



    def line_search(self):

        alpha = min(1.0, self.ccd_alpha())

        e_cur = self.compute_spring_energy(self.verts.x_k) + self.compute_collision_energy(self.verts.x_k)
        for i in range(5):
            self.add(self.x_t, self.verts.x_k, alpha, self.verts.dx)
            e = self.compute_spring_energy(self.x_t) + self.compute_collision_energy(self.x_t)
            if(e_cur < e):
                alpha /= 2.0
            else:
                # print(i)
                break
        return alpha

    @ti.kernel
    def compute_collision_energy(self, x: ti.template()) -> ti.f32:

        collision_e_total = 0.0
        for i in self.mmcvid:
            collision_e_total += self.compute_constraint_energy_PT(x, self.mmcvid[i][0], self.mmcvid[i][1])
        return collision_e_total
    @ti.kernel
    def compute_spring_energy(self, x: ti.template()) -> ti.f32:

        spring_e_total = 0.0
        for e in self.edges:
            v0, v1 = e.verts[0].id, e.verts[1].id
            xij = x[v0] - x[v1]
            l = xij.norm()
            coeff = 0.5 * self.dtSq * self.k
            spring_e_total += coeff * (l - e.l0) ** 2

        return spring_e_total

    @ti.kernel
    def modify_velocity(self):

        num = self.num_verts * self.num_faces_static
        # alpha = 1.0
        self.verts.p.fill(0.0)
        self.verts.nc.fill(0)
        for i in range(num):
            pid = i // self.num_faces_static
            fid = i % self.num_faces_static

            x0 = self.verts.x[pid]
            dx0 = self.verts.v[pid] * self.dt

            v1 = self.face_indices_static[3 * fid + 0]
            v2 = self.face_indices_static[3 * fid + 1]
            v3 = self.face_indices_static[3 * fid + 2]

            x1 = self.verts_static.x[v1]
            x2 = self.verts_static.x[v2]
            x3 = self.verts_static.x[v3]

            dx_zero = ti.math.vec3([0.0, 0.0, 0.0])

            alpha_ccd = ccd.point_triangle_ccd(x0, x1, x2, x3, dx0, dx_zero, dx_zero, dx_zero, 0.1, 1e-6, 1.0)

            self.verts.p[pid] += alpha_ccd * self.verts.v[pid]
            self.verts.nc[pid] += 1

        for v in self.verts:
            if v.nc > 1:
                v.v = v.p / v.nc

    @ti.kernel
    def apply_precondition(self, z: ti.template(), r: ti.template()):
        for i in z:
            z[i] = r[i] / self.verts.h[i]


    @ti.kernel
    def cg_iterate(self, r_2_new: ti.f32):

        # Ap = A * x
        for v in self.verts:
            self.Ap[v.id] = self.p[v.id] * v.m + v.h * self.p[v.id]

        ti.mesh_local(self.Ap, self.p)
        for e in self.edges:
            u = e.verts[0].id
            v = e.verts[1].id
            coeff = self.dtSq * self.k
            self.Ap[u] += coeff * self.p[v]
            self.Ap[v] += coeff * self.p[u]

        pAp = 0.0
        for v in self.verts:
            pAp += self.p[v.id].dot(self.Ap[v.id])

        alpha = r_2_new / pAp
        for v in self.verts:
            v.dx += alpha * self.p[v.id]
            self.r[v.id] -= alpha * self.Ap[v.id]

        for v in self.verts:
            self.z[v.id] = self.r[v.id] / v.h

    @ti.kernel
    def matrix_free_Ax(self, x: ti.template()):
        for v in self.verts:
            self.mul_ans[v.id] = x[v.id] * self.verts.m[v.id] + v.h * x[v.id]

        ti.mesh_local(self.mul_ans, x)
        for e in self.edges:
            u = e.verts[0].id
            v = e.verts[1].id
            coeff = self.dtSq * self.k
            self.mul_ans[u] += coeff * x[v]
            self.mul_ans[v] += coeff * x[u]

    def NewtonPCG(self):

        self.verts.dx.fill(0.0)
        self.r.copy_from(self.verts.g)

        self.apply_precondition(self.z, self.r)
        self.p.copy_from(self.z)
        r_2 = self.dot(self.z, self.r)
        n_iter = 10  # CG iterations
        epsilon = 1e-5
        r_2_init = r_2
        r_2_new = r_2

        for iter in range(n_iter):

            self.matrix_free_Ax(self.p)
            alpha = r_2_new / self.dot(self.p, self.mul_ans)
            self.add(self.verts.dx, self.verts.dx, alpha, self.p)
            self.add(self.r, self.r, -alpha, self.mul_ans)
            self.apply_precondition(self.z, self.r)

            r_2 = r_2_new
            r_2_new = self.dot(self.r, self.z)

            if r_2_new <= r_2_init * epsilon ** 2:
                break

            beta = r_2_new / r_2

            self.add(self.p, self.z, beta, self.p)


        self.add(self.verts.x_k, self.verts.x_k, -1.0, self.verts.dx)


    def update(self):

        self.verts.f_ext.fill([0.0, self.gravity, 0.0])
        self.computeVtemp()

        # for i in range(self.max_iter):
        #     self.modify_velocity()

        self.computeY()
        self.verts.x_k.copy_from(self.verts.y)

        for i in range(self.max_iter):
            self.verts.g.fill(0.)
            self.verts.h.copy_from(self.verts.m)
            self.evaluateSpringConstraint()
            self.computeConstraintSet()
            self.NewtonPCG()
            # self.compute_search_dir()
            # alpha = self.line_search()
            alpha = 1.0
            # self.step_forward(alpha)

        self.computeNextState()






