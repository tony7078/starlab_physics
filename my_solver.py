import taichi as ti
import meshtaichi_patcher as Patcher

@ti.dataclass
class contact_particle:
    vid: ti.u8
    w  : ti.math.vec3

@ti.data_oriented
class Solver:
    def __init__(self,
                 my_mesh,
                 static_mesh,
                 bottom,
                 k=1e4,
                 dt=1e-3,
                 max_iter=1000):
        self.my_mesh = my_mesh
        self.static_mesh = static_mesh
        self.k = k
        self.dt = dt
        self.dtSq = dt ** 2
        self.max_iter = max_iter
        self.gravity = -1.0
        self.bottom = bottom
        self.idenity3 = ti.math.mat3([[1, 0, 0],
                                      [0, 1, 0],
                                      [0, 0, 1]])

        self.radius = 0.003
        self.contact_stiffness = 1e3
        self.contact_particle = contact_particle.field(shape=(len(self.my_mesh.mesh.verts)))
        self.grid_n = 64
        self.grid_particles_list = ti.field(ti.i32)
        self.grid_block = ti.root.dense(ti.ijk, (self.grid_n, self.grid_n, self.grid_n))
        self.partical_array = self.grid_block.dynamic(ti.l, len(self.my_mesh.mesh.verts))
        self.partical_array.place(self.grid_particles_list)
        self.grid_particles_count = ti.field(ti.i32)
        ti.root.dense(ti.ijk, (self.grid_n, self.grid_n, self.grid_n)).place(self.grid_particles_count)
        print(f"verts #: {len(self.my_mesh.mesh.verts)}, elements #: {len(self.my_mesh.mesh.edges)}")
        # self.setRadius()
        print(f"radius: {self.radius}")


        self.initContactParticleData()


    # def setRadius(self):
    #     min = 100
    #
    #     for e in self.my_mesh.mesh.edges:
    #         if(min > e.l0):
    #             min = e.l0
    #
    #     self.radius = 0.4 * min

    @ti.func
    def resolve_contact(self, i, j):
        # test = i + j
        rel_pos = self.my_mesh.mesh.verts.x_k[j] - self.my_mesh.mesh.verts.x_k[i]
        dist = rel_pos.norm()
        delta = dist - 2 * self.radius  # delta = d - 2 * r
        coeff = self.contact_stiffness * self.dtSq
        if delta < 0:  # in contact
            normal = rel_pos / dist
            f1 = normal * delta * coeff
            # self.my_mesh.mesh.verts.grad[i] += f1
            # self.my_mesh.mesh.verts.grad[j] -= f1
            # self.my_mesh.mesh.verts.hii[i] += self.idenity3 * coeff
            # self.my_mesh.mesh.verts.hii[j] += self.idenity3 * coeff

    @ti.kernel
    def initContactParticleData(self):
        for c in self.contact_particle:
            self.contact_particle[c].vid = c

    @ti.kernel
    def computeNextState(self):
        for v in self.my_mesh.mesh.verts:
            v.v = (v.x_k - v.x) / self.dt
            v.x = v.x_k


    @ti.kernel
    def computeGradientAndElementWiseHessian(self):

        # momentum gradient M * (x - y) and hessian M
        for v in self.my_mesh.mesh.verts:
            v.grad = v.m * (v.x_k - v.y) - v.f * self.dtSq
            v.hii = v.m * self.idenity3

        # elastic energy gradient \nabla E (x)
        for e in self.my_mesh.mesh.edges:
            l = (e.verts[0].x_k - e.verts[1].x_k).norm()
            normal = (e.verts[0].x_k - e.verts[1].x_k).normalized(1e-12)
            coeff = self.dtSq * self.k
            grad_e = coeff * (l - e.l0) * normal
            e.verts[0].grad += grad_e
            e.verts[1].grad -= grad_e
            e.verts[0].hii += coeff * self.idenity3
            e.verts[1].hii += coeff * self.idenity3

        # handling bottom contact
        for v in self.my_mesh.mesh.verts:
            if (v.x_k[1] < 0):
                depth = v.x_k[1] - self.bottom
                up = ti.math.vec3(0, 1, 0)
                v.grad += self.dtSq * self.contact_stiffness * depth * up
                v.hii  += self.dtSq * self.contact_stiffness * self.idenity3

            if (v.x_k[1] > 1):
                depth = 1 - v.x_k[1]
                up = ti.math.vec3(0, -1, 0)
                v.grad += self.dtSq * self.contact_stiffness * depth * up
                v.hii  += self.dtSq * self.contact_stiffness * self.idenity3

            if (v.x_k[0] < 0):
                depth = v.x_k[0] - self.bottom
                up = ti.math.vec3(1, 0, 0)
                v.grad += self.dtSq * self.contact_stiffness * depth * up
                v.hii += self.dtSq * self.contact_stiffness * self.idenity3

            if (v.x_k[0] > 1):
                depth = 1 - v.x_k[0]
                up = ti.math.vec3(-1, 0, 0)
                v.grad += self.dtSq * self.contact_stiffness * depth * up
                v.hii += self.dtSq * self.contact_stiffness * self.idenity3

            if (v.x_k[2] < 0):
                depth = v.x_k[2] - self.bottom
                up = ti.math.vec3(0, 0, 1)
                v.grad += self.dtSq * self.contact_stiffness * depth * up
                v.hii += self.dtSq * self.contact_stiffness * self.idenity3

            if (v.x_k[2] > 1):
                depth = 1 - v.x_k[2]
                up = ti.math.vec3(0, 0, -1)
                v.grad += self.dtSq * self.contact_stiffness * depth * up
                v.hii += self.dtSq * self.contact_stiffness * self.idenity3

        # handling sphere contact
        for v in self.my_mesh.mesh.verts:
            center = ti.math.vec3(0, -0.3, 0)
            radius = 0.3
            dist = (v.x_k - center).norm()
            normal = (v.x_k - center).normalized(1e-6)
            if(dist < radius):
                coeff = self.dtSq * self.contact_stiffness
                v.grad += coeff * (dist - radius) * normal
                v.hii += coeff * self.idenity3

        self.grid_particles_count.fill(0)
        for v in self.my_mesh.mesh.verts:
            grid_idx = ti.floor(v.x_k * self.grid_n, int)
            ti.append(self.grid_particles_list.parent(), grid_idx, int(v.id))
            ti.atomic_add(self.grid_particles_count[grid_idx], 1)

        for v in self.my_mesh.mesh.verts:
            grid_idx = ti.floor(v.x_k * self.grid_n, int)
            x_begin = max(grid_idx[0] - 1, 0)
            x_end = min(grid_idx[0] + 2, self.grid_n)

            y_begin = max(grid_idx[1] - 1, 0)
            y_end = min(grid_idx[1] + 2, self.grid_n)

            z_begin = max(grid_idx[2] - 1, 0)
            # only need one side
            z_end = min(grid_idx[2] + 1, self.grid_n)

            # todo still serialize
            for neigh_i, neigh_j, neigh_k in ti.ndrange((x_begin, x_end), (y_begin, y_end), (z_begin, z_end)):

                # on split plane
                if neigh_k == grid_idx[2] and (neigh_i + neigh_j) > (grid_idx[0] + grid_idx[1]) and neigh_i <= grid_idx[0]:
                    continue
                # same grid
                iscur = neigh_i == grid_idx[0] and neigh_j == grid_idx[1] and neigh_k == grid_idx[2]
                for l in range(self.grid_particles_count[neigh_i, neigh_j, neigh_k]):
                    j = self.grid_particles_list[neigh_i, neigh_j, neigh_k, l]

                    if iscur and v.id >= j:
                        continue
                    self.resolve_contact(v.id, j)

        for v in self.my_mesh.mesh.verts:
            v.x_k -= v.hii.inverse() @ v.grad


    # @ti.kernel
    # def computeExternalForce(self):
    #     for v in self.my_mesh.mesh.verts:

    @ti.kernel
    def computeY(self):
        for v in self.my_mesh.mesh.verts:
            v.y = v.x + v.v * self.dt + (v.f / v.m) * self.dtSq

    def update(self):

        # self.computeExternalForce()
        self.my_mesh.mesh.verts.f.fill([0.0, self.gravity, 0.0])
        self.computeY()
        self.my_mesh.mesh.verts.x_k.copy_from(self.my_mesh.mesh.verts.y)
        for i in range(self.max_iter):
            self.computeGradientAndElementWiseHessian()

        self.computeNextState()


