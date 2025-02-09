import csv
import taichi as ti
import numpy as np
from framework.physics import collision_constraints_x, collision_constraints_v, pd_collision_x
from framework.collision.lbvh_cell import LBVH_CELL

@ti.data_oriented
class Solver:
    def __init__(self,
                 mesh_dy,
                 mesh_st,
                 dHat,
                 stiffness_stretch,
                 stiffness_bending,
                 g,
                 dt):

        self.mesh_dy = mesh_dy
        self.mesh_st = mesh_st
        self.g = g
        self.dt = dt
        self.dHat = dHat
        self.stiffness_stretch = stiffness_stretch
        self.stiffness_bending = stiffness_bending
        self.damping = 0.001
        self.mu = 0.8
        self.padding = 0.05

        self.solver_type = 0

        self.enable_velocity_update = True
        self.enable_collision_handling = True
        self.enable_move_obstacle = False
        self.export_mesh = False

        self.max_num_verts_dy = len(self.mesh_dy.verts)
        self.max_num_edges_dy = len(self.mesh_dy.edges)
        self.max_num_faces_dy = len(self.mesh_dy.faces)

        self.max_num_verts_st = 0
        self.max_num_edges_st = 0
        self.max_num_faces_st = 0

        # self.lbvh_st = None
        # if self.mesh_st != None:
        #     self.lbvh_st = LBVH_CELL(len(self.mesh_st.faces))
        #     self.max_num_verts_st = len(self.mesh_st.verts)
        #     self.max_num_edges_st = len(self.mesh_st.edges)
        #     self.max_num_faces_st = len(self.mesh_st.faces)

        # self.lbvh_dy = LBVH_CELL(len(self.mesh_dy.faces))
        self.vt_st_pair_cache_size = 40
        self.vt_st_candidates = ti.field(dtype=int)
        self.vt_st_candidates_num = ti.field(dtype=int)
        self.vt_st_pair = ti.field(dtype=int)
        self.vt_st_pair_num = ti.field(dtype=int)

        test = ti.root.dense(ti.i, self.max_num_verts_dy).place(self.vt_st_candidates_num,  self.vt_st_pair_num)
        test2 = test.dense(ti.j, self.vt_st_pair_cache_size)
        test2.place(self.vt_st_candidates)
        test2.dense(ti.k, 2).place(self.vt_st_pair)
        print(self.vt_st_pair.shape)

        # self.vt_st_candidates = ti.field(dtype=ti.int32, shape=(self.max_num_verts_dy, self.vt_st_pair_cache_size))
        # self.vt_st_candidates_num = ti.field(dtype=ti.int32, shape=self.max_num_verts_dy)
        # self.vt_st_pair = ti.field(dtype=ti.int32, shape=(self.max_num_verts_dy, self.vt_st_pair_cache_size, 2))
        # self.vt_st_pair_num = ti.field(dtype=ti.int32, shape=self.max_num_verts_dy)

        # self.vt_st_pair_g = ti.Vector.field(n=3, dtype=float, shape=(self.max_num_verts_dy, self.vt_st_pair_cache_size, 4))
        # self.vt_st_pair_schur = ti.field(dtype=float, shape=(self.max_num_verts_dy, self.vt_st_pair_cache_size))
        # self.tv_st_pair_cache_size = 40
        # self.tv_st_candidates = ti.field(dtype=ti.int32, shape=(self.max_num_verts_st, self.vt_st_pair_cache_size))
        # self.tv_st_candidates_num = ti.field(dtype=ti.int32, shape=self.max_num_verts_st)
        # self.tv_st_pair = ti.field(dtype=ti.int32, shape=(self.max_num_verts_st, self.tv_st_pair_cache_size, 2))
        # self.tv_st_pair_num = ti.field(dtype=ti.int32, shape=self.max_num_verts_st)
        # self.tv_st_pair_g = ti.Vector.field(n=3, dtype=float, shape=(self.max_num_verts_st, self.tv_st_pair_cache_size, 4))
        # self.tv_st_pair_schur = ti.field(dtype=float, shape=(self.max_num_verts_st, self.tv_st_pair_cache_size))
        #
        # self.vt_dy_pair_cache_size = 40
        # self.vt_dy_candidates = ti.field(dtype=ti.int32, shape=(self.max_num_verts_dy, self.vt_dy_pair_cache_size))
        # self.vt_dy_candidates_num = ti.field(dtype=ti.int32, shape=self.max_num_verts_dy)
        # self.vt_dy_pair = ti.field(dtype=ti.int32, shape=(self.max_num_verts_dy, self.vt_st_pair_cache_size, 2))
        # self.vt_dy_pair_num = ti.field(dtype=ti.int32, shape=self.max_num_verts_dy)
        # self.vt_dy_pair_g = ti.Vector.field(n=3, dtype=float, shape=(self.max_num_verts_dy, self.vt_st_pair_cache_size, 4))
        # self.vt_dy_pair_schur = ti.field(dtype=float, shape=(self.max_num_verts_dy, self.vt_st_pair_cache_size))

        # self.ee_st_pair_cache_size = 40
        # self.ee_st_candidates = ti.field(dtype=ti.int32, shape=(self.max_num_edges_dy, self.ee_st_pair_cache_size))
        # self.ee_st_candidates_num = ti.field(dtype=ti.int32, shape=self.max_num_edges_dy)
        # self.ee_st_pair = ti.field(dtype=ti.int32, shape=(self.max_num_edges_dy, self.ee_st_pair_cache_size, 2))
        # self.ee_st_pair_num = ti.field(dtype=ti.int32, shape=self.max_num_edges_dy)
        # self.ee_st_pair_g = ti.Vector.field(n=3, dtype=float, shape=(self.max_num_edges_dy, self.ee_st_pair_cache_size, 4))
        # self.ee_st_pair_schur = ti.field(dtype=float, shape=(self.max_num_edges_dy, self.ee_st_pair_cache_size))
        #
        # self.ee_dy_pair_cache_size = 40
        # self.ee_dy_candidates = ti.field(dtype=ti.int32, shape=(self.max_num_edges_dy, self.ee_dy_pair_cache_size))
        # self.ee_dy_candidates_num = ti.field(dtype=ti.int32, shape=self.max_num_edges_dy)
        # self.ee_dy_pair = ti.field(dtype=ti.int32, shape=(self.max_num_edges_dy, self.ee_dy_pair_cache_size, 2))
        # self.ee_dy_pair_num = ti.field(dtype=ti.int32, shape=self.max_num_edges_dy)
        # self.ee_dy_pair_g = ti.Vector.field(n=3, dtype=float, shape=(self.max_num_edges_dy, self.ee_dy_pair_cache_size, 4))
        # self.ee_dy_pair_schur = ti.field(dtype=float, shape=(self.max_num_edges_dy, self.ee_dy_pair_cache_size))

        # self.frame = ti.field(dtype=ti.i32, shape=1)
        # self.frame[0] = 0
        #
        # self.max_num_anim = 40
        # self.num_animation = ti.field(dtype=ti.i32, shape=4)   # maximum number of handle set
        # self.cur_animation = ti.field(dtype=ti.i32, shape=4)   # maximum number of handle set
        # self.anim_rotation_mat = ti.Matrix.field(4, 4, dtype=float, shape=4)
        #
        # self.anim_local_origin = ti.Vector.field(3, dtype=float, shape=4)
        # self.active_anim_frame = ti.field(dtype=ti.i32, shape=(4, self.max_num_anim)) # maximum number of animation
        # self.action_anim = ti.Vector.field(6, dtype=float, shape=(4, self.max_num_anim)) # maximum number of animation, a animation consist (vx,vy,vz,rx,ry,rz)
        # self.anim_x = ti.Vector.field(n=3, dtype=float, shape=self.max_num_verts_dynamic)

        self.sewing_pairs = ti.Vector.field(n=2, dtype=ti.int32, shape=(self.max_num_verts_dy))
        self.sewing_pairs_num = ti.field(dtype=ti.int32, shape=())
        self.sewing_pairs_num[None] = 0

        self.bd_max = ti.math.vec3(15.0)
        self.bd_min = -self.bd_max
        self.grid_size = (64, 64, 64)
        self.cell_size = (self.bd_max - self.bd_min)[0] / self.grid_size[0]
        self.grid_num_particles = ti.field(int)
        self.particles2grid = ti.field(int)
        self.cell_cache_size = 100
        grid_snode = ti.root.dense(ti.ijk, (4, 4, 4)).dense(ti.ijk, (4, 4, 4)).dense(ti.ijk, (4, 4, 4))
        grid_snode.place(self.grid_num_particles)
        grid_snode.dense(ti.l, self.cell_cache_size).place(self.particles2grid)

        self.aabb_x0 = ti.Vector.field(n=3, dtype=float, shape=8)
        self.aabb_index0 = ti.field(dtype=int, shape=24)
        self.init_grid(self.bd_min, self.bd_max)

    @ti.func
    def pos_to_cell_id(self, y: ti.math.vec3) -> ti.math.ivec3:
        test = (y - self.bd_min) / self.cell_size
        return ti.cast(test, int)


    @ti.func
    def confine_boundary(self, p):
        boundary_min = self.bd_min + self.padding
        boundary_max = self.bd_max - self.padding

        for i in ti.static(range(3)):
            if p[i] <= boundary_min[i]:
                p[i] = boundary_min[i] + 1e-4 * ti.random()
            elif boundary_max[i] <= p[i]:
                p[i] = boundary_max[i] - 1e-4 * ti.random()

        return p

    @ti.func
    def is_in_grid(self, c):
        # @c: Vector(i32)

        is_in_grid = True
        for i in ti.static(range(3)):
            is_in_grid = is_in_grid and (0 <= c[i] < self.grid_size[i])

        return is_in_grid

    @ti.kernel
    def init_grid(self, bd_min: ti.math.vec3, bd_max: ti.math.vec3):

        aabb_min = bd_min
        aabb_max = bd_max

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

    # @ti.func
    # def pos_to_cell_id(self, y: ti.math.vec3, bbmin: ti.math.vec3, bbmax: ti.math.vec3) -> ti.math.ivec3:
    #
    #     test = (y - bbmin) / self.cell_size
    #     return ti.cast(test, int)

    def reset(self):

        self.mesh_dy.reset()
        if self.mesh_st != None:
            self.mesh_st.reset()

    @ti.kernel
    def compute_y(self, g: ti.math.vec3, dt: float):
        for v in self.mesh_dy.verts:
            v.y = v.x + v.fixed * (v.v * dt + g * dt * dt)
            v.y = self.confine_boundary(v.y)

        # path_len = self.mesh_dy.path_euler.shape[0]
        # # print(path_len)
        # for i in range(path_len):
        #     self.mesh_dy.y_euler[i] = self.mesh_dy.x_euler[i] + self.mesh_dy.fixed_euler[i] * (self.mesh_dy.v_euler[i] * dt + self.g * dt * dt)

    @ti.func
    def is_in_face(self, vid, fid):

        v1 = self.mesh_dy.face_indices[3 * fid + 0]
        v2 = self.mesh_dy.face_indices[3 * fid + 1]
        v3 = self.mesh_dy.face_indices[3 * fid + 2]

        return (v1 == vid) or (v2 == vid) or (v3 == vid)

    @ti.func
    def share_vertex(self, ei0, ei1):

        v0 = self.mesh_dy.edge_indices[2 * ei0 + 0]
        v1 = self.mesh_dy.edge_indices[2 * ei0 + 1]
        v2 = self.mesh_dy.edge_indices[2 * ei1 + 0]
        v3 = self.mesh_dy.edge_indices[2 * ei1 + 1]

        return (v0 == v2) or (v0 == v3) or (v1 == v2) or (v1 == v3)

    # @ti.kernel
    # def ThomasAlgorithm(self):


    @ti.kernel
    def solve_spring_constraints_jacobi_x(self, compliance_stretch: float, compliance: float):

        # for v in self.mesh_dy.verts:
        #     v.y = v.x + v.fixed * (v.v * dt + g * dt * dt)

        self.mesh_dy.verts.dx.fill(0.0)
        self.mesh_dy.verts.nc.fill(0.0)

        for i in range(self.max_num_edges_dy):

            # solve stretch constraints
            if i < self.max_num_edges_dy:
                bi = i
                l0 = self.mesh_dy.edges.l0[bi]
                v0, v1 = self.mesh_dy.edge_indices[2 * bi], self.mesh_dy.edge_indices[2 * bi + 1]
                x10 = self.mesh_dy.verts.y[v0] - self.mesh_dy.verts.y[v1]
                lij = x10.norm()

                C = (lij - l0)
                nabla_C = x10.normalized()
                schur = (self.mesh_dy.verts.fixed[v0] * self.mesh_dy.verts.m_inv[v0] + self.mesh_dy.verts.fixed[v1] * self.mesh_dy.verts.m_inv[v1])

                ld = compliance_stretch * C / (compliance_stretch * schur + 1.0)

                self.mesh_dy.verts.dx[v0] -= self.mesh_dy.verts.fixed[v0] * self.mesh_dy.verts.m_inv[v0] * ld * nabla_C
                self.mesh_dy.verts.dx[v1] += self.mesh_dy.verts.fixed[v1] * self.mesh_dy.verts.m_inv[v1] * ld * nabla_C
                self.mesh_dy.verts.nc[v0] += 1.0
                self.mesh_dy.verts.nc[v1] += 1.0

            # solve stretch constraints
            else:
                bi = i - self.max_num_edges_dy
                v0, v1 = self.mesh_dy.bending_indices[2 * bi], self.mesh_dy.bending_indices[2 * bi + 1]
                l0 = self.mesh_dy.bending_l0[bi]
                x10 = self.mesh_dy.verts.x[v0] - self.mesh_dy.verts.x[v1]
                lij = x10.norm()

                C = (lij - l0)
                nabla_C = x10.normalized()

                e_v0_fixed, e_v1_fixed = self.mesh_dy.verts.fixed[v0], self.mesh_dy.verts.fixed[v1]
                e_v0_m_inv, e_v1_m_inv = self.mesh_dy.verts.m_inv[v0], self.mesh_dy.verts.m_inv[v1]

                schur = (e_v0_fixed * e_v0_m_inv + e_v1_fixed * e_v1_m_inv)
                ld = compliance * C / (compliance * schur + 1.0)

                self.mesh_dy.verts.dx[v0] -= e_v0_fixed * e_v0_m_inv * ld * nabla_C
                self.mesh_dy.verts.dx[v1] += e_v1_fixed * e_v1_m_inv * ld * nabla_C
                self.mesh_dy.verts.nc[v0] += 1.0
                self.mesh_dy.verts.nc[v1] += 1.0

        for v in self.mesh_dy.verts:
            v.y += v.fixed * (v.dx / v.nc)

    @ti.kernel
    def solve_spring_constraints_pd_diag_x(self, g: ti.math.vec3, dt: float, compliance_stretch: float, compliance_bending: float,
                                           enable_collision: bool, cell_size_st: ti.math.vec3, origin_st: ti.math.vec3, cell_size_dy: ti.math.vec3, origin_dy: ti.math.vec3,
                                           damping: float, compliance_col: float,
                                           enable_velocity_update: bool, mu: float):

        for v in self.mesh_dy.verts:
            v.y = v.x + v.fixed * (v.v * dt + g * dt * dt)

        self.mesh_dy.verts.gii.fill(0.0)
        self.mesh_dy.verts.hii.fill(1.0)
        # self.mesh_dy.verts.nc.fill(0.0)

        for i in range(self.max_num_edges_dy):
            # solve stretch constraints
            if i < self.max_num_edges_dy:
                bi = i
                l0 = self.mesh_dy.edges.l0[bi]
                v0, v1 = self.mesh_dy.edge_indices[2 * bi], self.mesh_dy.edge_indices[2 * bi + 1]
                x01 = self.mesh_dy.verts.y[v0] - self.mesh_dy.verts.y[v1]
                lij = x01.norm()

                C = (lij - l0)
                nabla_C = x01.normalized()
                schur = (self.mesh_dy.verts.fixed[v0] * self.mesh_dy.verts.m_inv[v0] + self.mesh_dy.verts.fixed[v1] * self.mesh_dy.verts.m_inv[v1])

                k = 1e8
                ld = k * C / (k * schur + 1.0)

                p01 = x01 - schur * ld * nabla_C

                self.mesh_dy.verts.gii[v0] += self.mesh_dy.verts.fixed[v0] * self.mesh_dy.verts.m_inv[v0] * compliance_stretch * (x01 - p01)
                self.mesh_dy.verts.gii[v1] -= self.mesh_dy.verts.fixed[v1] * self.mesh_dy.verts.m_inv[v1] * compliance_stretch * (x01 - p01)

                self.mesh_dy.verts.hii[v0] += self.mesh_dy.verts.fixed[v0] * self.mesh_dy.verts.m_inv[v0] * compliance_stretch
                self.mesh_dy.verts.hii[v1] += self.mesh_dy.verts.fixed[v1] * self.mesh_dy.verts.m_inv[v1] * compliance_stretch
                # self.mesh_dy.verts.nc[v0] += 1.0
                # self.mesh_dy.verts.nc[v1] += 1.0

            # solve stretch constraints
            else:
                bi = i - self.max_num_edges_dy
                v0, v1 = self.mesh_dy.bending_indices[2 * bi], self.mesh_dy.bending_indices[2 * bi + 1]
                l0 = self.mesh_dy.bending_l0[bi]
                x01 = self.mesh_dy.verts.x[v0] - self.mesh_dy.verts.x[v1]
                lij = x01.norm()

                C = (lij - l0)
                nabla_C = x01.normalized()

                e_v0_fixed, e_v1_fixed = self.mesh_dy.verts.fixed[v0], self.mesh_dy.verts.fixed[v1]
                e_v0_m_inv, e_v1_m_inv = self.mesh_dy.verts.m_inv[v0], self.mesh_dy.verts.m_inv[v1]

                schur = (e_v0_fixed * e_v0_m_inv + e_v1_fixed * e_v1_m_inv)
                k = 1e8
                ld = k * C / (k * schur + 1.0)

                p01 = x01 - schur * ld * nabla_C

                self.mesh_dy.verts.gii[v0] += e_v0_fixed * e_v0_m_inv * compliance_bending * (x01 - p01)
                self.mesh_dy.verts.gii[v1] -= e_v1_fixed * e_v1_m_inv * compliance_bending * (x01 - p01)
                self.mesh_dy.verts.hii[v0] += e_v0_fixed * e_v0_m_inv * compliance_bending
                self.mesh_dy.verts.hii[v1] += e_v1_fixed * e_v1_m_inv * compliance_bending
                # self.mesh_dy.verts.nc[v0] += 1.0
                # self.mesh_dy.verts.nc[v1] += 1.0

        # for v in self.mesh_dy.verts:
        #     if v.nc > 0:
        #         v.y += v.fixed * (v.dx / v.nc)

        self.vt_st_candidates_num.fill(0)
        self.tv_st_candidates_num.fill(0)
        self.vt_dy_candidates_num.fill(0)
        size = ti.cast(enable_collision, int) * (2 * self.max_num_verts_dy + self.max_num_verts_st)
        # print(size)
        for i in range(size):
            if i < self.max_num_verts_dy:
                vid = i
                y = self.mesh_dy.verts.y[vid]
                aabb_min = y - self.padding * ti.math.vec3(1.0)
                aabb_max = y + self.padding * ti.math.vec3(1.0)
                self.lbvh_st.traverse_cell_bvh_single(cell_size_st, origin_st, aabb_min, aabb_max, vid,
                                                      self.vt_st_candidates, self.vt_st_candidates_num)

            elif i < 2 * self.max_num_verts_dy:
                vid = i - self.max_num_verts_dy
                y = self.mesh_dy.verts.y[vid]
                aabb_min = y - self.padding * ti.math.vec3(1.0)
                aabb_max = y + self.padding * ti.math.vec3(1.0)
                self.lbvh_dy.traverse_cell_bvh_single(cell_size_dy, origin_dy, aabb_min, aabb_max, vid,
                                                      self.vt_dy_candidates, self.vt_dy_candidates_num)

            else:
                vid = i - 2 * self.max_num_verts_dy
                x = self.mesh_st.verts.x[vid]
                aabb_min = x - self.padding * ti.math.vec3(1.0)
                aabb_max = x + self.padding * ti.math.vec3(1.0)
                self.lbvh_dy.traverse_cell_bvh_single(cell_size_dy, origin_dy, aabb_min, aabb_max, vid, self.tv_st_candidates, self.tv_st_candidates_num)

    # self.ee_st_candidates_num.fill(0)
    # self.ee_dy_candidates_num.fill(0)
    #
    # for i in range(2 * self.max_num_edges_dy):
    #     if i < self.max_num_edges_dy:
    #         ii = i
    #         v0, v1 = self.mesh_dy.edge_indices[2 * ii], self.mesh_dy.edge_indices[2 * ii + 1]
    #         aabb_min = ti.math.min(self.mesh_dy.verts.y[v0], self.mesh_dy.verts.y[v1]) - self.padding * ti.math.vec3(1.0)
    #         aabb_max = ti.math.max(self.mesh_dy.verts.y[v0], self.mesh_dy.verts.y[v1]) + self.padding * ti.math.vec3(1.0)
    #         self.lbvh_st.traverse_cell_bvh_single(cell_size_st, origin_st, aabb_min, aabb_max, ii, self.ee_st_candidates, self.ee_st_candidates_num)
    #     else:
    #         ii = i - self.max_num_edges_dy
    #         v0, v1 = self.mesh_dy.edge_indices[2 * ii], self.mesh_dy.edge_indices[2 * ii + 1]
    #         aabb_min = ti.math.min(self.mesh_dy.verts.y[v0], self.mesh_dy.verts.y[v1]) - self.padding * ti.math.vec3(1.0)
    #         aabb_max = ti.math.max(self.mesh_dy.verts.y[v0],self.mesh_dy.verts.y[v1]) + self.padding * ti.math.vec3(1.0)
    #         self.lbvh_dy.traverse_cell_bvh_single(cell_size_st, origin_st, aabb_min, aabb_max, ii, self.ee_dy_candidates, self.ee_dy_candidates_num)

        self.vt_st_pair_num.fill(0)
        self.tv_st_pair_num.fill(0)
        self.vt_dy_pair_num.fill(0)
        # self.ee_st_pair_num.fill(0)
        # self.ee_dy_pair_num.fill(0)

        # self.mesh_dy.verts.dx.fill(0.0)
        # self.mesh_dy.verts.nc.fill(0.0)
        # compliance_vt_st = 1e5 * dt * dt
        d = self.dHat
        size = ti.cast(enable_collision, int) * (2 * self.max_num_verts_dy + self.max_num_verts_st)
        for i in range(size):

            if i < self.max_num_verts_dy:
                vid = i
                for j in range(self.vt_st_candidates_num[vid]):
                    fi_s = self.vt_st_candidates[vid, j]
                    pd_collision_x.__vt_st(compliance_col, vid, fi_s, self.mesh_dy, self.mesh_st, d, self.vt_st_pair_cache_size, self.vt_st_pair, self.vt_st_pair_num, self.vt_st_pair_g, self.vt_st_pair_schur)

            elif i < 2 * self.max_num_verts_dy:
                vid = i - self.max_num_verts_dy
                # for j in range(self.vt_dy_candidates_num[vid]):
                #     fi_d = self.vt_dy_candidates[vid, j]
                #     if self.is_in_face(vid, fi_d) != True:
                #         pd_collision_x.__vt_dy(vid, fi_d, self.mesh_dy, d, self.vt_st_pair_cache_size, self.vt_dy_pair, self.vt_dy_pair_num, self.vt_dy_pair_g, self.vt_dy_pair_schur)
            else:
                vis = i - 2 * self.max_num_verts_dy
                for j in range(self.tv_st_candidates_num[vis]):
                    fi_d = self.tv_st_candidates[vis, j]
                    pd_collision_x.__tv_st(compliance_col, fi_d, vis, self.mesh_dy, self.mesh_st, d, self.vt_st_pair_cache_size, self.tv_st_pair, self.tv_st_pair_num, self.tv_st_pair_g, self.tv_st_pair_schur)

        for v in self.mesh_dy.verts:
            # if v.nc > 0:
            v.y -= (v.gii / v.hii)
            v.v = (1.0 - damping) * (v.y - v.x) / dt

        self.mesh_dy.verts.dv.fill(0.0)
        self.mesh_dy.verts.nc.fill(0.0)
        size = ti.cast(enable_velocity_update, int) * ti.cast(enable_collision, int) * (2 * self.max_num_verts_dy + self.max_num_verts_st)

        # print(size)
        for i in range(size):
            if i < self.max_num_verts_dy:
                vid = i
                # for vid in range(self.max_num_verts_dy):
                for j in range(self.vt_st_pair_num[vid]):
                    fi_s, dtype = self.vt_st_pair[vid, j, 0], self.vt_st_pair[vid, j, 1]
                    g0, g1, g2, g3 = self.vt_st_pair_g[vid, j, 0], self.vt_st_pair_g[vid, j, 1], self.vt_st_pair_g[
                        vid, j, 2], self.vt_st_pair_g[vid, j, 3]
                    schur = self.vt_st_pair_schur[vid, j]
                    collision_constraints_v.__vt_st(vid, fi_s, dtype, self.mesh_dy, self.mesh_st, g0, g1, g2, g3, schur, mu)

            elif i < 2 * self.max_num_verts_dy:
                vid = i - self.max_num_verts_dy
                for j in range(self.vt_dy_pair_num[vid]):
                    fi_d, dtype = self.vt_dy_pair[vid, j, 0], self.vt_dy_pair[vid, j, 1]
                    g0, g1, g2, g3 = self.vt_dy_pair_g[vid, j, 0], self.vt_dy_pair_g[vid, j, 1], self.vt_dy_pair_g[
                        vid, j, 2], self.vt_dy_pair_g[vid, j, 3]
                    schur = self.vt_dy_pair_schur[vid, j]
                    collision_constraints_v.__vt_dy(vid, fi_d, dtype, self.mesh_dy, g0, g1, g2, g3, schur, mu)

            else:
                vis = i - 2 * self.max_num_verts_dy
                for j in range(self.tv_st_pair_num[vis]):
                    fi_d, dtype = self.tv_st_pair[vis, j, 0], self.tv_st_pair[vis, j, 1]
                    g0, g1, g2, g3 = self.tv_st_pair_g[vis, j, 0], self.tv_st_pair_g[vis, j, 1], self.tv_st_pair_g[
                        vis, j, 2], self.tv_st_pair_g[vis, j, 3]
                    schur = self.tv_st_pair_schur[vis, j]
                    collision_constraints_v.__tv_st(fi_d, vis, dtype, self.mesh_dy, self.mesh_st, g0, g1, g2, g3, schur, mu)

        for v in self.mesh_dy.verts:
            if v.nc > 0:
                v.v += (v.dv / v.nc)
        # for v in self.mesh_dy.verts:
        #     v.v = (1.0 - damping) * v.fixed * (v.y - v.x) / dt

        for v in self.mesh_dy.verts:
            # if v.id != 0:
            v.x += dt * v.v



    @ti.kernel
    def solve_stretch_constraints_gauss_seidel_x(self, compliance_stretch: float):

        ti.loop_config(serialize=True)
        for i in range(self.max_num_edges_dy):
            # solve stretch constraints
            # if i < self.max_num_edges_dy:
            bi = i
            l0 = self.mesh_dy.edges.l0[bi]
            v0, v1 = self.mesh_dy.edge_indices[2 * bi], self.mesh_dy.edge_indices[2 * bi + 1]
            x10 = self.mesh_dy.verts.y[v0] - self.mesh_dy.verts.y[v1]
            lij = x10.norm()

            C = (lij - l0)
            nabla_C = x10.normalized()
            schur = (self.mesh_dy.verts.fixed[v0] * self.mesh_dy.verts.m_inv[v0] + self.mesh_dy.verts.fixed[v1] *
                     self.mesh_dy.verts.m_inv[v1])

            ld = compliance_stretch * C / (compliance_stretch * schur + 1.0)

            self.mesh_dy.verts.y[v0] -= self.mesh_dy.verts.fixed[v0] * self.mesh_dy.verts.m_inv[v0] * ld * nabla_C
            self.mesh_dy.verts.y[v1] += self.mesh_dy.verts.fixed[v1] * self.mesh_dy.verts.m_inv[v1] * ld * nabla_C
            # self.mesh_dy.verts.nc[v0] += 1.0
            # self.mesh_dy.verts.nc[v1] += 1.0

    @ti.kernel
    def compute_grad_and_hessian_stretch_constraints_jacobi_DOT_x(self, compliance_stretch: float):

        for i in range(self.max_num_edges_dy):
            bi = i
            l0 = self.mesh_dy.edges.l0[bi]
            v0, v1 = self.mesh_dy.edge_indices[2 * bi], self.mesh_dy.edge_indices[2 * bi + 1]
            x01 = self.mesh_dy.verts.y[v0] - self.mesh_dy.verts.y[v1]
            lij = x01.norm()

            C = (lij - l0)
            nabla_C = x01.normalized()
            schur = (self.mesh_dy.verts.fixed[v0] * self.mesh_dy.verts.m_inv[v0] +
                     self.mesh_dy.verts.fixed[v1] * self.mesh_dy.verts.m_inv[v1])

            k = 1e8
            ld = k * C / (k * schur + 1.0)

            p01 = x01 - schur * ld * nabla_C

            self.mesh_dy.verts.gii[v0] += self.mesh_dy.verts.fixed[v0] * self.mesh_dy.verts.m_inv[v0] * compliance_stretch * (x01 - p01)
            self.mesh_dy.verts.gii[v1] -= self.mesh_dy.verts.fixed[v1] * self.mesh_dy.verts.m_inv[v1] * compliance_stretch * (x01 - p01)

            self.mesh_dy.verts.hii[v0] += self.mesh_dy.verts.fixed[v0] * self.mesh_dy.verts.m_inv[v0] * compliance_stretch
            self.mesh_dy.verts.hii[v1] += self.mesh_dy.verts.fixed[v1] * self.mesh_dy.verts.m_inv[v1] * compliance_stretch

            self.mesh_dy.verts.nc[v0] += 1.0
            self.mesh_dy.verts.nc[v1] += 1.0

        for i in range(self.max_num_edges_dy):
            v0, v1 = self.mesh_dy.edge_indices[2 * i], self.mesh_dy.edge_indices[2 * i + 1]
            m_inv0, m_inv1 = self.mesh_dy.verts.fixed[v0] * self.mesh_dy.verts.m_inv[v0], self.mesh_dy.verts.fixed[v1] * \
                             self.mesh_dy.verts.m_inv[v1]
            g0, g1 = self.mesh_dy.verts.gii[v0], self.mesh_dy.verts.gii[v1]
            h0, h1 = self.mesh_dy.verts.hii[v0], self.mesh_dy.verts.hii[v1]

            det = h0 * h1 - m_inv0 * m_inv1 * compliance_stretch * compliance_stretch

            self.mesh_dy.verts.dx[v0] -= (h1 * g0 - m_inv0 * compliance_stretch * g1) / det
            self.mesh_dy.verts.dx[v1] -= (-m_inv1 * compliance_stretch * g0 + h0 * g1) / det

        for v in self.mesh_dy.verts:
            v.y += (v.dx / v.nc)


    @ti.kernel
    def solve_jacobi_DOT_x(self, compliance_stretch: float):

        for i in range(self.max_num_edges_dy):
            v0, v1 = self.mesh_dy.edge_indices[2 * i], self.mesh_dy.edge_indices[2 * i + 1]
            m_inv0, m_inv1 = self.mesh_dy.verts.fixed[v0] * self.mesh_dy.verts.m_inv[v0], self.mesh_dy.verts.fixed[v1] * self.mesh_dy.verts.m_inv[v1]
            g0, g1 = self.mesh_dy.verts.gii[v0], self.mesh_dy.verts.gii[v1]
            h0, h1 = self.mesh_dy.verts.hii[v0], self.mesh_dy.verts.hii[v1]

            det = h0 * h1 - m_inv0 * m_inv1 * compliance_stretch * compliance_stretch

            self.mesh_dy.verts.dx[v0] -= (h1 * g0 - m_inv0 * compliance_stretch * g1) / det
            self.mesh_dy.verts.dx[v1] -= (-m_inv1 * compliance_stretch * g0 + h0 * g1) / det

        for i in range(self.max_num_edges_dy):
            v0, v1 = self.mesh_dy.edge_indices[2 * i], self.mesh_dy.edge_indices[2 * i + 1]
            m_inv0, m_inv1 = self.mesh_dy.verts.fixed[v0] * self.mesh_dy.verts.m_inv[v0], self.mesh_dy.verts.fixed[v1] * self.mesh_dy.verts.m_inv[v1]
            g0, g1 = self.mesh_dy.verts.gii[v0], self.mesh_dy.verts.gii[v1]
            h0, h1 = self.mesh_dy.verts.hii[v0], self.mesh_dy.verts.hii[v1]

            det = h0 * h1 - m_inv0 * m_inv1 * compliance_stretch * compliance_stretch

            self.mesh_dy.verts.dx[v0] -= (h1 * g0 - m_inv0 * compliance_stretch * g1) / det
            self.mesh_dy.verts.dx[v1] -= (-m_inv1 * compliance_stretch * g0 + h0 * g1) / det

    @ti.kernel
    def solve_bending_constraints_gauss_seidel_x(self, compliance_bending: float):

        ti.loop_config(serialize=True)
        for i in range(self.max_num_edges_dy):
            bi = i
            v0, v1 = self.mesh_dy.bending_indices[2 * bi], self.mesh_dy.bending_indices[2 * bi + 1]
            l0 = self.mesh_dy.bending_l0[bi]
            x10 = self.mesh_dy.verts.x[v0] - self.mesh_dy.verts.x[v1]
            lij = x10.norm()

            C = (lij - l0)
            nabla_C = x10.normalized()

            e_v0_fixed, e_v1_fixed = self.mesh_dy.verts.fixed[v0], self.mesh_dy.verts.fixed[v1]
            e_v0_m_inv, e_v1_m_inv = self.mesh_dy.verts.m_inv[v0], self.mesh_dy.verts.m_inv[v1]

            schur = (e_v0_fixed * e_v0_m_inv + e_v1_fixed * e_v1_m_inv) * nabla_C.dot(nabla_C)
            ld = compliance_bending * C / (compliance_bending * schur + 1.0)

            self.mesh_dy.verts.y[v0] -= e_v0_fixed * e_v0_m_inv * ld * nabla_C
            self.mesh_dy.verts.y[v1] += e_v1_fixed * e_v1_m_inv * ld * nabla_C
            # self.mesh_dy.verts.nc[v0] += 1.0
            # self.mesh_dy.verts.nc[v1] += 1.0

    @ti.kernel
    def broadphase_lbvh(self, cell_size_st: ti.math.vec3, origin_st: ti.math.vec3, cell_size_dy: ti.math.vec3, origin_dy: ti.math.vec3, damping:float, dt:float, compliance_col: float, enable_collision: bool):

        # self.vt_st_candidates_num.fill(0)
        # self.tv_st_candidates_num.fill(0)
        # self.vt_dy_candidates_num.fill(0)
        #
        # size = ti.cast(enable_collision, int) * (2 * self.max_num_verts_dy + self.max_num_verts_st)
        # for i in range(size):
        #
        #     if i < self.max_num_verts_dy:
        #         vid = i
        #         y = self.mesh_dy.verts.y[vid]
        #         aabb_min = y - self.padding * ti.math.vec3(1.0)
        #         aabb_max = y + self.padding * ti.math.vec3(1.0)
        #         self.lbvh_st.traverse_cell_bvh_single(cell_size_st, origin_st, aabb_min, aabb_max, vid, self.vt_st_candidates, self.vt_st_candidates_num)
        #
        #     elif i < 2 * self.max_num_verts_dy:
        #         vid = i - self.max_num_verts_dy
        #         y = self.mesh_dy.verts.y[vid]
        #         aabb_min = y - self.padding * ti.math.vec3(1.0)
        #         aabb_max = y + self.padding * ti.math.vec3(1.0)
        #         self.lbvh_dy.traverse_cell_bvh_single(cell_size_dy, origin_dy, aabb_min, aabb_max, vid, self.vt_dy_candidates, self.vt_dy_candidates_num)
        #
        #     else:
        #         vid = i - 2 * self.max_num_verts_dy
        #         x = self.mesh_st.verts.x[vid]
        #         aabb_min = x - self.padding * ti.math.vec3(1.0)
        #         aabb_max = x + self.padding * ti.math.vec3(1.0)
        #         self.lbvh_dy.traverse_cell_bvh_single(cell_size_dy, origin_dy, aabb_min, aabb_max, vid, self.tv_st_candidates, self.tv_st_candidates_num)

        # self.ee_st_candidates_num.fill(0)
        # self.ee_dy_candidates_num.fill(0)
        #
        # for i in range(2 * self.max_num_edges_dy):
        #     if i < self.max_num_edges_dy:
        #         ii = i
        #         v0, v1 = self.mesh_dy.edge_indices[2 * ii], self.mesh_dy.edge_indices[2 * ii + 1]
        #         aabb_min = ti.math.min(self.mesh_dy.verts.y[v0], self.mesh_dy.verts.y[v1]) - self.padding * ti.math.vec3(1.0)
        #         aabb_max = ti.math.max(self.mesh_dy.verts.y[v0], self.mesh_dy.verts.y[v1]) + self.padding * ti.math.vec3(1.0)
        #         self.lbvh_st.traverse_cell_bvh_single(cell_size_st, origin_st, aabb_min, aabb_max, ii, self.ee_st_candidates, self.ee_st_candidates_num)
        #     else:
        #         ii = i - self.max_num_edges_dy
        #         v0, v1 = self.mesh_dy.edge_indices[2 * ii], self.mesh_dy.edge_indices[2 * ii + 1]
        #         aabb_min = ti.math.min(self.mesh_dy.verts.y[v0], self.mesh_dy.verts.y[v1]) - self.padding * ti.math.vec3(1.0)
        #         aabb_max = ti.math.max(self.mesh_dy.verts.y[v0],self.mesh_dy.verts.y[v1]) + self.padding * ti.math.vec3(1.0)
        #         self.lbvh_dy.traverse_cell_bvh_single(cell_size_st, origin_st, aabb_min, aabb_max, ii, self.ee_dy_candidates, self.ee_dy_candidates_num)

        self.vt_st_pair_num.fill(0)
        self.tv_st_pair_num.fill(0)
        self.vt_dy_pair_num.fill(0)
        # self.ee_st_pair_num.fill(0)
        # self.ee_dy_pair_num.fill(0)

        # self.mesh_dy.verts.dx.fill(0.0)
        # self.mesh_dy.verts.nc.fill(0.0)

        d = self.dHat
        for i in range(2 * self.max_num_verts_dy + self.max_num_verts_st):

            if i < self.max_num_verts_dy:
                vid = i
                for j in range(self.vt_st_candidates_num[vid]):
                    fi_s = self.vt_st_candidates[vid, j]
                    collision_constraints_x.__vt_st(compliance_col, vid, fi_s, self.mesh_dy, self.mesh_st, d,
                                                    self.vt_st_pair_cache_size, self.vt_st_pair, self.vt_st_pair_num,
                                                    self.vt_st_pair_g, self.vt_st_pair_schur)

            elif i < 2 * self.max_num_verts_dy:
                vid = i - self.max_num_verts_dy
                # for j in range(self.vt_dy_candidates_num[vid]):
                #     fi_d = self.vt_dy_candidates[vid, j]
                #     if self.is_in_face(vid, fi_d) != True:
                #         collision_constraints_x.__vt_dy(vid, fi_d, self.mesh_dy, d, self.vt_st_pair_cache_size,
                #                                         self.vt_dy_pair, self.vt_dy_pair_num, self.vt_dy_pair_g,
                #                                         self.vt_dy_pair_schur)
            else:
                vis = i - 2 * self.max_num_verts_dy
                for j in range(self.tv_st_candidates_num[vis]):
                    fi_d = self.tv_st_candidates[vis, j]
                    collision_constraints_x.__tv_st(compliance_col, fi_d, vis, self.mesh_dy, self.mesh_st, d,
                                                    self.vt_st_pair_cache_size, self.tv_st_pair, self.tv_st_pair_num,
                                                    self.tv_st_pair_g, self.tv_st_pair_schur)

        for v in self.mesh_dy.verts:
            # if v.nc > 0:
            v.y += v.fixed * (v.dx / v.nc)
            v.v = (1.0 - damping) * (v.y - v.x) / dt

        # for v in self.mesh_dy.verts:
        #     v.v = (1.0 - damping) * v.fixed * (v.y - v.x) / dt

        for v in self.mesh_dy.verts:
            # if v.id != 0:
            v.x += dt * v.v

    @ti.kernel
    def broadphase_pd_diag_lbvh(self, cell_size_st: ti.math.vec3, origin_st: ti.math.vec3, cell_size_dy: ti.math.vec3,
                        origin_dy: ti.math.vec3, damping: float, dt: float, compliance_col: float):

        self.vt_st_candidates_num.fill(0)
        self.tv_st_candidates_num.fill(0)
        self.vt_dy_candidates_num.fill(0)

        for i in range(2 * self.max_num_verts_dy + self.max_num_verts_st):

            if i < self.max_num_verts_dy:
                vid = i
                y = self.mesh_dy.verts.y[vid]
                aabb_min = y - self.padding * ti.math.vec3(1.0)
                aabb_max = y + self.padding * ti.math.vec3(1.0)
                self.lbvh_st.traverse_cell_bvh_single(cell_size_st, origin_st, aabb_min, aabb_max, vid, self.vt_st_candidates, self.vt_st_candidates_num)

            elif i < 2 * self.max_num_verts_dy:
                vid = i - self.max_num_verts_dy
                y = self.mesh_dy.verts.y[vid]
                aabb_min = y - self.padding * ti.math.vec3(1.0)
                aabb_max = y + self.padding * ti.math.vec3(1.0)
                self.lbvh_dy.traverse_cell_bvh_single(cell_size_dy, origin_dy, aabb_min, aabb_max, vid, self.vt_dy_candidates, self.vt_dy_candidates_num)

            else:
                vid = i - 2 * self.max_num_verts_dy
                x = self.mesh_st.verts.x[vid]
                aabb_min = x - self.padding * ti.math.vec3(1.0)
                aabb_max = x + self.padding * ti.math.vec3(1.0)
                self.lbvh_dy.traverse_cell_bvh_single(cell_size_dy, origin_dy, aabb_min, aabb_max, vid, self.tv_st_candidates, self.tv_st_candidates_num)

        # self.ee_st_candidates_num.fill(0)
        # self.ee_dy_candidates_num.fill(0)
        #
        # for i in range(2 * self.max_num_edges_dy):
        #     if i < self.max_num_edges_dy:
        #         ii = i
        #         v0, v1 = self.mesh_dy.edge_indices[2 * ii], self.mesh_dy.edge_indices[2 * ii + 1]
        #         aabb_min = ti.math.min(self.mesh_dy.verts.y[v0], self.mesh_dy.verts.y[v1]) - self.padding * ti.math.vec3(1.0)
        #         aabb_max = ti.math.max(self.mesh_dy.verts.y[v0], self.mesh_dy.verts.y[v1]) + self.padding * ti.math.vec3(1.0)
        #         self.lbvh_st.traverse_cell_bvh_single(cell_size_st, origin_st, aabb_min, aabb_max, ii, self.ee_st_candidates, self.ee_st_candidates_num)
        #     else:
        #         ii = i - self.max_num_edges_dy
        #         v0, v1 = self.mesh_dy.edge_indices[2 * ii], self.mesh_dy.edge_indices[2 * ii + 1]
        #         aabb_min = ti.math.min(self.mesh_dy.verts.y[v0], self.mesh_dy.verts.y[v1]) - self.padding * ti.math.vec3(1.0)
        #         aabb_max = ti.math.max(self.mesh_dy.verts.y[v0],self.mesh_dy.verts.y[v1]) + self.padding * ti.math.vec3(1.0)
        #         self.lbvh_dy.traverse_cell_bvh_single(cell_size_st, origin_st, aabb_min, aabb_max, ii, self.ee_dy_candidates, self.ee_dy_candidates_num)

        self.vt_st_pair_num.fill(0)
        self.tv_st_pair_num.fill(0)
        self.vt_dy_pair_num.fill(0)
        # self.ee_st_pair_num.fill(0)
        # self.ee_dy_pair_num.fill(0)

        # self.mesh_dy.verts.dx.fill(0.0)
        # self.mesh_dy.verts.nc.fill(0.0)

        d = self.dHat
        for i in range(2 * self.max_num_verts_dy + self.max_num_verts_st):

            if i < self.max_num_verts_dy:
                vid = i
                for j in range(self.vt_st_candidates_num[vid]):
                    fi_s = self.vt_st_candidates[vid, j]
                    pd_collision_x.__vt_st(compliance_col, vid, fi_s, self.mesh_dy, self.mesh_st, d, self.vt_st_pair_cache_size, self.vt_st_pair, self.vt_st_pair_num, self.vt_st_pair_g, self.vt_st_pair_schur)
            #
            # elif i < 2 * self.max_num_verts_dy:
            #     vid = i - self.max_num_verts_dy
            #     for j in range(self.vt_dy_candidates_num[vid]):
            #         fi_d = self.vt_dy_candidates[vid, j]
            #         if self.is_in_face(vid, fi_d) != True:
            #             pd_collision_x.__vt_dy(vid, fi_d, self.mesh_dy, d, self.vt_st_pair_cache_size, self.vt_dy_pair, self.vt_dy_pair_num, self.vt_dy_pair_g, self.vt_dy_pair_schur)
            # else:
            #     vis = i - 2 * self.max_num_verts_dy
            #     for j in range(self.tv_st_candidates_num[vis]):
            #         fi_d = self.tv_st_candidates[vis, j]
            #         pd_collision_x.__tv_st(compliance_col, fi_d, vis, self.mesh_dy, self.mesh_st, d, self.vt_st_pair_cache_size, self.tv_st_pair, self.tv_st_pair_num, self.tv_st_pair_g, self.tv_st_pair_schur)

        for v in self.mesh_dy.verts:
            # if v.nc > 0:
            v.y -= (v.gii / v.hii)
            v.v = (1.0 - damping) * (v.y - v.x) / dt

        # for v in self.mesh_dy.verts:
        #     v.v = (1.0 - damping) * v.fixed * (v.y - v.x) / dt

        for v in self.mesh_dy.verts:
            # if v.id != 0:
            v.x += dt * v.v



    @ti.kernel
    def solve_collision_constraints_x(self, compliance_col: float, d: float):

        # self.vt_st_pair_num.fill(0)
        # self.tv_st_pair_num.fill(0)
        # self.vt_dy_pair_num.fill(0)
        # self.ee_st_pair_num.fill(0)
        # self.ee_dy_pair_num.fill(0)

        self.mesh_dy.verts.dx.fill(0.0)
        self.mesh_dy.verts.nc.fill(0.0)

        # d = self.dHat
        # for i in range(2 * self.max_num_verts_dy + self.max_num_verts_st):
        #
        #     if i < self.max_num_verts_dy:
        #         vid = i
        #         for j in range(self.vt_st_candidates_num[vid]):
        #             fi_s = self.vt_st_candidates[vid, j]
        #             collision_constraints_x.__vt_st(compliance_col, vid, fi_s, self.mesh_dy, self.mesh_st, d, self.vt_st_pair_cache_size, self.vt_st_pair, self.vt_st_pair_num, self.vt_st_pair_g, self.vt_st_pair_schur)
        #
        #     elif i < 2 * self.max_num_verts_dy:
        #         vid = i - self.max_num_verts_dy
        #         for j in range(self.vt_dy_candidates_num[vid]):
        #             fi_d = self.vt_dy_candidates[vid, j]
        #             if self.is_in_face(vid, fi_d) != True:
        #                 collision_constraints_x.__vt_dy(vid, fi_d, self.mesh_dy, d, self.vt_st_pair_cache_size, self.vt_dy_pair, self.vt_dy_pair_num, self.vt_dy_pair_g, self.vt_dy_pair_schur)
        #     else:
        #         vis = i - 2 * self.max_num_verts_dy
        #         for j in range(self.tv_st_candidates_num[vis]):
        #             fi_d = self.tv_st_candidates[vis, j]
        #             collision_constraints_x.__tv_st(compliance_col, fi_d, vis, self.mesh_dy, self.mesh_st, d, self.vt_st_pair_cache_size, self.tv_st_pair, self.tv_st_pair_num, self.tv_st_pair_g, self.tv_st_pair_schur)

        # for f in self.mesh_st.faces:
        #
        #     bbmin = ti.math.min(f.verts.x[0], f.verts.x[1], f.verts.x[2])
        #     bbmax = ti.math.max(f.verts.x[0], f.verts.x[1], f.verts.x[2])


        for v in self.mesh_dy.verts:
            cell_id = self.pos_to_cell_id(v.y)
            for offs in ti.static(ti.grouped(ti.ndrange((-1, 2), (-1, 2), (-1, 2)))):
                cell_to_check = cell_id + offs
                if self.is_in_grid(cell_to_check):
                    for j in range(self.grid_num_particles[cell_to_check]):
                        vj = self.particles2grid[cell_to_check, j]
                        pos_j = self.mesh_st.verts.x[vj]
                        xji = pos_j - v.y
                        if xji.norm() < 2.0 * d:
                            dir = ti.math.normalize(xji)
                            self.mesh_dy.verts.dx[v.id] += ((xji.norm() - 2.0 * d) * dir)
                            self.mesh_dy.verts.nc[v.id] += 1
                        # collision_constraints_x.__vt_st(compliance_col, v.id, fj, self.mesh_dy, self.mesh_st, d)

        for v in self.mesh_dy.verts:
            if v.nc > 0:
                v.y += v.fixed * (v.dx / v.nc)
        #
        # for v in self.mesh_dy.verts:
        #     v.v = (1.0 - damping) * v.fixed * (v.y - v.x) / dt

        # for i in range(2 * self.max_num_edges_dy):
        #     if i < self.max_num_edges_dy:
        #         eid = i
        #         for j in range(self.ee_st_candidates_num[eid]):
        #             fis = self.ee_st_candidates[eid, j]
        #             for k in range(3):
        #                 eis = self.mesh_st.face_edge_indices[3 * fis + k]
        #                 collision_constraints_x.__ee_st(compliance_col, eid, eis, self.mesh_dy, self.mesh_st, d, self.ee_st_pair_cache_size, self.ee_st_pair, self.ee_st_pair_num, self.ee_st_pair_g, self.ee_st_pair_schur)
        #     else:
        #         eid = i - self.max_num_edges_dy
        #         for j in range(self.ee_dy_candidates_num[eid]):
        #             fid = self.ee_dy_candidates[eid, j]
        #             for k in range(3):
        #                 ejd = self.mesh_dy.face_edge_indices[3 * fid + k]
        #                 if self.share_vertex(eid, ejd) == False:
        #                     collision_constraints_x.__ee_dy(compliance_col, eid, ejd, self.mesh_dy, d, self.ee_dy_pair_cache_size, self.ee_dy_pair, self.ee_dy_pair_num, self.ee_dy_pair_g, self.ee_dy_pair_schur)

    @ti.kernel
    def solve_collision_constraints_v(self, mu: float):

        for i in range(2 * self.max_num_verts_dy + self.max_num_verts_st):

            if i < self.max_num_verts_dy:
                vid = i
        # for vid in range(self.max_num_verts_dy):
                for j in range(self.vt_st_pair_num[vid]):
                    fi_s, dtype = self.vt_st_pair[vid, j, 0], self.vt_st_pair[vid, j, 1]
                    g0, g1, g2, g3 = self.vt_st_pair_g[vid, j, 0], self.vt_st_pair_g[vid, j, 1], self.vt_st_pair_g[vid, j, 2], self.vt_st_pair_g[vid, j, 3]
                    schur = self.vt_st_pair_schur[vid, j]
                    collision_constraints_v.__vt_st(vid, fi_s, dtype, self.mesh_dy, self.mesh_st, g0, g1, g2, g3, schur, mu)

            elif i < 2 * self.max_num_verts_dy:
                vid = i - self.max_num_verts_dy
                for j in range(self.vt_dy_pair_num[vid]):
                    fi_d, dtype = self.vt_dy_pair[vid, j, 0], self.vt_dy_pair[vid, j, 1]
                    g0, g1, g2, g3 = self.vt_dy_pair_g[vid, j, 0], self.vt_dy_pair_g[vid, j, 1], self.vt_dy_pair_g[vid, j, 2], self.vt_dy_pair_g[vid, j, 3]
                    schur = self.vt_dy_pair_schur[vid, j]
                    collision_constraints_v.__vt_dy(vid, fi_d, dtype, self.mesh_dy, g0, g1, g2, g3, schur, mu)

            else:
                vis = i - 2 * self.max_num_verts_dy
                for j in range(self.tv_st_pair_num[vis]):
                    fi_d, dtype = self.tv_st_pair[vis, j, 0], self.tv_st_pair[vis, j, 1]
                    g0, g1, g2, g3 = self.tv_st_pair_g[vis, j, 0],  self.tv_st_pair_g[vis, j, 1],  self.tv_st_pair_g[vis, j, 2],  self.tv_st_pair_g[vis, j, 3]
                    schur = self.tv_st_pair_schur[vis, j]
                    collision_constraints_v.__tv_st(fi_d, vis, dtype, self.mesh_dy, self.mesh_st, g0, g1, g2, g3, schur, mu)

        # for i in range(2 * self.max_num_edges_dy):
        #     if i < self.max_num_edges_dy:
        #         ei_d = i
        #         for j in range(self.ee_st_pair_num[ei_d]):
        #             # eis = self.mesh_st.face_edge_indices[3 * fis + k]
        #             ei_s, dtype = self.ee_st_pair[ei_d, j, 0], self.ee_st_pair[ei_d, j, 1]
        #             g0, g1, g2, g3 = self.ee_st_pair_g[ei_d, j, 0], self.ee_st_pair_g[ei_d, j, 1], self.ee_st_pair_g[ei_d, j, 2], self.ee_st_pair_g[ei_d, j, 3]
        #             schur = self.ee_st_pair_schur[ei_d, j]
        #             collision_constraints_v.__ee_st(ei_d, ei_s, dtype, self.mesh_dy, self.mesh_st, g0, g1, g2, g3, schur, mu)
        #
        #     else:
        #         ei_d = i - self.max_num_edges_dy
        #         for j in range(self.ee_dy_pair_num[ei_d]):
        #             # eis = self.mesh_st.face_edge_indices[3 * fis + k]
        #             ej_d, dtype = self.ee_dy_pair[ei_d, j, 0], self.ee_dy_pair[ei_d, j, 1]
        #             g0, g1, g2, g3 = self.ee_dy_pair_g[ei_d, j, 0], self.ee_st_pair_g[ei_d, j, 1], self.ee_st_pair_g[ei_d, j, 2], self.ee_dy_pair_g[ei_d, j, 3]
        #             schur = self.ee_dy_pair_schur[ei_d, j]
        #             collision_constraints_v.__ee_dy(ei_d, ej_d, self.mesh_dy, g0, g1, g2, g3, schur, mu)

    @ti.kernel
    def update_x(self, dt: float):

        for v in self.mesh_dy.verts:
            # if v.id != 0:
            v.x += dt * v.v
            v.x = self.confine_boundary(v.x)

        # path_len = self.mesh_dy.path_euler.shape[0]
        # # print(path_len)
        # for i in range(path_len):
        #     self.mesh_dy.x_euler[i] += (self.mesh_dy.v_euler[i] * dt)
        #
        # for i in range(path_len - 1):
        #     v0, v1 = self.mesh_dy.edge_indices_euler[2 * i + 0], self.mesh_dy.edge_indices_euler[2 * i + 1]
        #     self.mesh_dy.colored_edge_pos_euler[i] = 0.5 * (self.mesh_dy.x_euler[v0] + self.mesh_dy.x_euler[v1])

            # if i % 2 == 0:
            #     self.mesh_dy.colored_edge_pos_euler[i] = ti.math.vec3(1.0, 0.0, 0.0)
            # else:
            #     self.mesh_dy.colored_edge_pos_euler[i] = ti.math.vec3(0.0, 0.0, 1.0)



    @ti.kernel
    def compute_velocity(self, damping: float, dt: float):
        for v in self.mesh_dy.verts:
            v.v = (1.0 - damping) * v.fixed * (v.y - v.x) / dt

        # path_len = self.mesh_dy.path_euler.shape[0]
        # # print(path_len)
        # for i in range(path_len):
        #     self.mesh_dy.v_euler[i] = self.mesh_dy.fixed_euler[i] * (1.0 - damping) * (self.mesh_dy.y_euler[i] - self.mesh_dy.x_euler[i]) / dt

    def init_variables(self):

        self.mesh_dy.verts.dx.fill(0.0)
        self.mesh_dy.verts.nc.fill(0.0)

    def solve_constraints_jacobi_x(self, dt):

        # self.init_variables()

        compliance_stretch = self.stiffness_stretch * dt * dt
        compliance_bending = self.stiffness_bending * dt * dt
        self.solve_spring_constraints_jacobi_x(compliance_stretch, compliance_bending)

    def solve_pd_diag_x(self, dt):

        # self.init_variables()
        compliance_stretch = self.stiffness_stretch * dt * dt
        compliance_bending = self.stiffness_bending * dt * dt
        compliance_collision = 1e1 * compliance_stretch

        self.solve_spring_constraints_pd_diag_x(self.g, dt, compliance_stretch, compliance_bending,
                                                self.enable_collision_handling, self.lbvh_st.cell_size, self.lbvh_st.origin, self.lbvh_dy.cell_size, self.lbvh_dy.origin, self.damping, compliance_collision, self.enable_velocity_update, self.mu)

        # self.update_dx()
        # if self.enable_collision_handling:
        #     compliance_collision = 1e8 * dt * dt
        #     self.broadphase_pd_diag_lbvh(self.lbvh_st.cell_size, self.lbvh_st.origin, self.lbvh_dy.cell_size, self.lbvh_dy.origin, self.damping, dt, compliance_collision)

            # self.init_variables()

            # compliance_collision = 1e8
            # self.solve_collision_constraints_x(self.damping, dt, compliance_collision)
            # self.update_dx()

    def solve_constraints_jacobi_DOT_x(self, dt):

        self.init_variables()

        compliance_stretch = self.stiffness_stretch * dt * dt
        self.mesh_dy.verts.gii.fill(0.0)
        self.mesh_dy.verts.hii.fill(1.0)
        self.compute_grad_and_hessian_stretch_constraints_jacobi_DOT_x(compliance_stretch)

        # self.solve_jacobi_DOT_x(compliance_stretch)

        # self.update_jacobi_DOT_dx()

        if self.enable_collision_handling:

            self.broadphase_lbvh(self.lbvh_st.cell_size, self.lbvh_st.origin, self.lbvh_dy.cell_size, self.lbvh_dy.origin)

            self.init_variables()

            compliance_collision = 1e8
            self.solve_collision_constraints_x(compliance_collision)
            self.update_dx()

    @ti.kernel
    def update_jacobi_DOT_dx(self):
        for v in self.mesh_dy.verts:
            v.y += (v.dx / v.nc)

    def solve_constraints_gauss_seidel_x(self, dt):

        self.init_variables()

        compliance_stretch = self.stiffness_stretch * dt * dt
        compliance_bending = self.stiffness_bending * dt * dt

        self.solve_stretch_constraints_gauss_seidel_x(compliance_stretch)
        # self.solve_bending_constraints_gauss_seidel_x(compliance_bending)

        # if self.enable_collision_handling:
        #     self.broadphase_lbvh(self.lbvh_st.cell_size, self.lbvh_st.origin, self.lbvh_dy.cell_size, self.lbvh_dy.origin)
        #
        #     # self.init_variables()
        #
        #     compliance_collision = 1e8
        #     self.solve_collision_constraints_x(compliance_collision)
        #     self.update_dx()

        # compliance_sewing = 0.5 * self.YM * dt * dt
        # self.solve_sewing_constraints_x(compliance_sewing)

    #pgs(parallel gauss-seidel via graph coloring)
    def solve_constraints_euler_pgs_x(self, dt):

        # self.copy_to_duplicates()

        compliance_stretch = self.stiffness_stretch * dt * dt
        compliance_bending = self.stiffness_bending * dt * dt

        l0_len = self.mesh_dy.x_euler.shape[0] - 1
        size1 = size0 = l0_len // 2

        if l0_len % 2 == 1:
            size0 += 1

        self.solve_stretch_constraints_euler_x(compliance_stretch, size0, 0)
        self.solve_stretch_constraints_euler_x(compliance_stretch, size1, 1)

        self.mesh_dy.verts.y.fill(0.0)
        self.aggregate_duplicates()

    #ls: linear solve
    def solve_constraints_euler_ls_x(self, dt):

        # self.copy_to_duplicates()

        # self.mesh_dy.fixed_euler[0] = 0.0
        # self.mesh_dy.fixed_euler[self.mesh_dy.path_euler.shape[0] - 2] = 0.0

        compliance_stretch = self.stiffness_stretch * dt * dt
        self.mesh_dy.a_euler.fill(0.0)
        self.mesh_dy.b_euler.fill(1.0)
        self.mesh_dy.c_euler.fill(0.0)
        self.mesh_dy.g_euler.fill(0.0)
        self.mesh_dy.d_tilde_euler.fill(0.0)
        self.mesh_dy.c_tilde_euler.fill(0.0)

        self.compute_grad_and_hessian_stretch_constraints_euler_x(compliance_stretch)

        # a = self.mesh_dy.a_euler.to_numpy()
        # a = a[: -1]
        # b = self.mesh_dy.b_euler.to_numpy()
        # c = self.mesh_dy.c_euler.to_numpy()
        # c = c[1:]
        #
        # tri_diag_mat = np.diag(b) + np.diag(a, k=1) + np.diag(c, k=-1)
        #
        # print(tri_diag_mat)

        # print(self.mesh_dy.b_euler)
        # print(self.mesh_dy.c_euler)

        # self.compute_global_hessian_euler_x()

        # a = self.mesh_dy.a_euler.to_numpy()
        # a = a[: -1]
        # b = self.mesh_dy.b_euler.to_numpy()
        # c = self.mesh_dy.c_euler.to_numpy()
        # c = c[1:]
        #
        # tri_diag_mat = np.diag(b) + np.diag(a, k=1) + np.diag(c, k=-1)

        # print(tri_diag_mat)

        # self.mesh_dy.dx_euler.copy_from(self.mesh_dy.g_euler)
        self.solve_ls_thomas_euler_x(a=self.mesh_dy.a_euler, b=self.mesh_dy.b_euler, c=self.mesh_dy.c_euler, d=self.mesh_dy.g_euler,
                                      c_tilde=self.mesh_dy.c_tilde_euler, d_tilde=self.mesh_dy.d_tilde_euler, dx=self.mesh_dy.dx_euler)

        # dx = self.mesh_dy.dx_euler

        self.update_y_euler()

        self.mesh_dy.verts.y.fill(0.0)
        # self.aggregate_duplicates()

    @ti.kernel
    def aggregate_duplicates(self):

        path_len = self.mesh_dy.path_euler.shape[0]
        # print(path_len)
        # ti.loop_config(serialize=True)
        for i in range(path_len):
            vid = self.mesh_dy.path_euler[i]
            self.mesh_dy.verts.y[vid] += self.mesh_dy.y_euler[i]

        for v in self.mesh_dy.verts:
            v.y /= v.dup

        for i in range(path_len):
            vid = self.mesh_dy.path_euler[i]
            self.mesh_dy.y_euler[i] = self.mesh_dy.verts.y[vid]

    @ti.kernel
    def copy_to_duplicates(self):

        path_len = self.mesh_dy.path_euler.shape[0]
        # print(path_len)
        for i in range(path_len):
            vid = self.mesh_dy.path_euler[i]
            # self.mesh_dy.y_euler[i] = self.mesh_dy.verts.y[vid]
            self.mesh_dy.m_inv_euler[i] = self.mesh_dy.verts.m_inv[vid]
            self.mesh_dy.fixed_euler[i] = self.mesh_dy.verts.fixed[vid]

    @ti.kernel
    def solve_stretch_constraints_euler_x(self, compliance_stretch: float, size: ti.int32, offset: ti.i32):

        path_len = self.mesh_dy.path_euler.shape[0]
        # print(self.mesh_dy.l0_euler.shape[0])
        # ti.loop_config(serialize=True)
        for i in range(size):
            i_color = 2 * i + offset
            v0, v1 = self.mesh_dy.edge_indices_euler[2 * i_color + 0], self.mesh_dy.edge_indices_euler[2 * i_color + 1]
            l0 = self.mesh_dy.l0_euler[i_color]
            x10 = self.mesh_dy.y_euler[v0] - self.mesh_dy.y_euler[v1]
            lij = x10.norm()
            C = (lij - l0)
            nabla_C = x10.normalized()
            schur = (self.mesh_dy.fixed_euler[v0] * self.mesh_dy.m_inv_euler[v0] + self.mesh_dy.fixed_euler[v1] * self.mesh_dy.m_inv_euler[v1])

            ld = compliance_stretch * C / (compliance_stretch * schur + 1.0)

            self.mesh_dy.y_euler[v0] -= self.mesh_dy.fixed_euler[v0] * self.mesh_dy.m_inv_euler[v0] * ld * nabla_C
            self.mesh_dy.y_euler[v1] += self.mesh_dy.fixed_euler[v1] * self.mesh_dy.m_inv_euler[v1] * ld * nabla_C

    @ti.kernel
    def compute_grad_and_hessian_stretch_constraints_euler_x(self, compliance_stretch: float):

        for i in range(self.max_num_edges_dy):
            bi = i
            l0 = self.mesh_dy.edges.l0[bi]
            v0, v1 = self.mesh_dy.edge_indices[2 * bi], self.mesh_dy.edge_indices[2 * bi + 1]
            x01 = self.mesh_dy.verts.y[v0] - self.mesh_dy.verts.y[v1]
            lij = x01.norm()

            C = (lij - l0)
            nabla_C = x01.normalized()
            schur = (self.mesh_dy.verts.fixed[v0] * self.mesh_dy.verts.m_inv[v0] +
                     self.mesh_dy.verts.fixed[v1] * self.mesh_dy.verts.m_inv[v1])

            k = 1e8
            ld = k * C / (k * schur + 1.0)
            p01 = x01 - schur * ld * nabla_C

            self.mesh_dy.verts.gii[v0] += self.mesh_dy.verts.fixed[v0] * self.mesh_dy.verts.m_inv[v0] * compliance_stretch * (x01 - p01)
            self.mesh_dy.verts.gii[v1] -= self.mesh_dy.verts.fixed[v1] * self.mesh_dy.verts.m_inv[v1] * compliance_stretch * (x01 - p01)

            self.mesh_dy.verts.hii[v0] += self.mesh_dy.verts.fixed[v0] * self.mesh_dy.verts.m_inv[v0] * compliance_stretch
            self.mesh_dy.verts.hii[v1] += self.mesh_dy.verts.fixed[v1] * self.mesh_dy.verts.m_inv[v1] * compliance_stretch

    @ti.kernel
    def compute_global_hessian_euler_x(self):

        path_len = self.mesh_dy.path_euler.shape[0]
        for i in range(path_len):
            m_inv = self.mesh_dy.fixed_euler[i] * self.mesh_dy.m_inv_euler[i]
            self.mesh_dy.a_euler[i] *= m_inv
            # self.mesh_dy.b_euler[i] *= m_inv
            # self.mesh_dy.b_euler[i] = 1.0 + m_inv * self.mesh_dy.b_euler[i]
            self.mesh_dy.c_euler[i + 1] *= m_inv
            self.mesh_dy.g_euler[i] *= m_inv


    @ti.kernel
    def solve_ls_thomas_euler_x(self, a: ti.template(), b: ti.template(), c: ti.template(), d: ti.template(),
                                                                      c_tilde: ti.template(), d_tilde: ti.template(), dx: ti.template()):



        numVerts = b.shape[0]
        #
        # for i in range(numVerts):
        #     dx[i] = d[i] / b[i]
        c_tilde[0] = c[0] / b[0]

        ti.loop_config(serialize=True)
        for i in range(numVerts - 2):
            id = i + 1
            # print(id)
            c_tilde[id] = c[id] / (b[id] - a[id] * c[id - 1])

        # print("_______________")
        d_tilde[0] = d[0] / b[0]

        ti.loop_config(serialize=True)
        for i in range(numVerts - 1):
            id = i + 1
            # print(id)
            d_tilde[id] = (d[id] - a[id] * d_tilde[id - 1]) / (b[id] - a[id] * c_tilde[id - 1])
        #
        dx[numVerts - 1] = d[numVerts - 1]

        ti.loop_config(serialize=True)
        for i in range(numVerts - 1):
            id = numVerts - 2 - i
            dx[id] = d_tilde[id] - c_tilde[id] * dx[id + 1]

    def solve_constraints_v(self):
        self.mesh_dy.verts.dv.fill(0.0)
        self.mesh_dy.verts.nc.fill(0.0)

        if self.enable_collision_handling:
            self.solve_collision_constraints_v(self.mu)

        self.update_dv()

    @ti.kernel
    def update_dx(self):
        for v in self.mesh_dy.verts:
            if v.nc > 0:
                v.y += v.fixed * (v.dx / v.nc)

        # path_len = self.mesh_dy.path_euler.shape[0]
        # for i in range(path_len):
        #     vid = self.mesh_dy.path_euler[i]
        #     self.mesh_dy.y_euler[i] = self.mesh_dy.verts.y[vid]



    @ti.kernel
    def update_y_euler(self):
        path_len = self.mesh_dy.path_euler.shape[0]
        for i in range(path_len):
            self.mesh_dy.y_euler[i] += self.mesh_dy.dx_euler[i]

    @ti.kernel
    def set_fixed_vertices(self, fixed_vertices: ti.template()):
        for v in self.mesh_dy.verts:
            if fixed_vertices[v.id] >= 1:
                v.fixed = 0.0
            else:
                v.fixed = 1.0

    @ti.kernel
    def update_dv(self):
        for v in self.mesh_dy.verts:
            if v.nc > 0.0:
                v.dv = v.dv / v.nc

            if v.m_inv > 0.0:
                v.v += v.fixed * v.dv


    def load_sewing_pairs(self):
        data = []

        with open('animation/sewing.csv', 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            data = list(reader)

        data_np = np.array(data, dtype=np.int32)
        self.copy_sewing_pairs_to_taichi_field(data_np, len(data_np))
        self.sewing_pairs_num[None] = len(data_np)
        # print(self.sewing_pairs)

    @ti.kernel
    def copy_sewing_pairs_to_taichi_field(self, data_np: ti.types.ndarray(), length: ti.i32):
        for i in range(length):
            self.sewing_pairs[i] = ti.Vector([data_np[i, 0], data_np[i, 1]])


    @ti.kernel
    def solve_sewing_constraints_x(self, compliance: float):
        for i in range(self.sewing_pairs_num[None]):
            v1_id = self.sewing_pairs[i][0]
            v2_id = self.sewing_pairs[i][1]
            v1_y = self.mesh_dy.verts.y[v1_id]
            v2_y = self.mesh_dy.verts.y[v2_id]

            C = (v2_y - v1_y).norm()
            nabla_C = (v1_y - v2_y).normalized()
            schur = (self.mesh_dy.verts.fixed[v1_id] * self.mesh_dy.verts.m_inv[v1_id] + self.mesh_dy.verts.fixed[v2_id] * self.mesh_dy.verts.m_inv[v2_id])
            ld = compliance * C / (compliance * schur + 1.0)

            self.mesh_dy.verts.dx[v1_id] -= self.mesh_dy.verts.fixed[v1_id] * self.mesh_dy.verts.m_inv[v1_id] * ld * nabla_C
            self.mesh_dy.verts.dx[v2_id] += self.mesh_dy.verts.fixed[v2_id] * self.mesh_dy.verts.m_inv[v2_id] * ld * nabla_C
            self.mesh_dy.verts.nc[v1_id] += 1.0
            self.mesh_dy.verts.nc[v2_id] += 1.0

    @ti.kernel
    def search_neighbours(self):

        self.grid_num_particles.fill(0)
        # ti.block_local(self.x_p, self.grid_num_particles, self.particles2grid)

        # for f in self.mesh_st.faces:
        # # for pi in self.x_p:
        #     center = 0.33 * (f.verts[0].x + f.verts[1].x + f.verts[2].x)
        #     cell_id = self.pos_to_cell_id(center)
        #     counter = ti.atomic_add(self.grid_num_particles[cell_id], 1)
        #     if counter < self.cell_cache_size:
        #         self.particles2grid[cell_id, counter] = f.id
        for v in self.mesh_st.verts:
        # for pi in self.x_p:
        #     center = 0.33 * (f.verts[0].x + f.verts[1].x + f.verts[2].x)
            cell_id = self.pos_to_cell_id(v.x)
            counter = ti.atomic_add(self.grid_num_particles[cell_id], 1)
            if counter < self.cell_cache_size:
                self.particles2grid[cell_id, counter] = v.id

    def forward(self, n_substeps):

        dt_sub = self.dt / n_substeps
        for _ in range(n_substeps):
            self.compute_y(self.g, dt_sub)
            self.solve_constraints_jacobi_x(dt_sub)
            self.compute_velocity(damping=self.damping, dt=dt_sub)
            self.update_x(dt=dt_sub)

