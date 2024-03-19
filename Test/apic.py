import taichi as ti
import numpy as np
ti.init(arch=ti.gpu) # Try to run on GPU
quality = 1 # Use a larger value for higher-res simulations
n_particles, n_grid = 9000 * quality ** 2, 128 * quality
dx, inv_dx = 1 / n_grid, float(n_grid)
dt = 1e-4 / quality
p_vol, p_rho = (dx * 0.5)**2, 1
p_mass = p_vol * p_rho
E, nu = 0.1e4, 0.2 # Young's modulus and Poisson's ratio
mu_0, lambda_0 = E / (2 * (1 + nu)), E * nu / ((1+nu) * (1 - 2 * nu)) # Lame parameters
x = ti.Vector.field(2, dtype=float, shape=n_particles) # position
v = ti.Vector.field(2, dtype=float, shape=n_particles) # velocity
C = ti.Matrix.field(2, 2, dtype=float, shape=n_particles) # affine velocity field
F = ti.Matrix.field(2, 2, dtype=float, shape=n_particles) # deformation gradient
material = ti.field(dtype=int, shape=n_particles) # material id
Jp = ti.field(dtype=float, shape=n_particles) # plastic deformation
grid_v = ti.Vector.field(2, dtype=float, shape=(n_grid, n_grid)) # grid node momentum/velocity
grid_m = ti.field(dtype=float, shape=(n_grid, n_grid)) # grid node mass

@ti.kernel
def substep():
  for i, j in grid_m:
    grid_v[i, j] = [0, 0]
    grid_m[i, j] = 0

  for p in x: # Particle state update and scatter to grid (P2G)
    base = (x[p] * inv_dx).cast(int)
    fx = x[p] * inv_dx - base.cast(float)
    # Cubic kernels http://mpm.graphics Eqn. 122 with x=fx+1, fx, abs(fx-1), abs(fx-2)
    w = [1./6.*(2. - (fx + 1))**3, 0.5*fx**3 - fx**2 + 2./3., 0.5*(-(fx - 1.))**3 - (-(fx - 1.))**2 + 2./3., 1./6.*(2. + (fx - 2.))**3]
    F[p] = (ti.Matrix.identity(float, 2) + dt * C[p]) @ F[p] # deformation gradient update
    h = ti.exp(10 * (1.0 - Jp[p])) # Hardening coefficient: snow gets harder when compressed
    if material[p] == 1: # jelly, make it softer
      h = 0.3
    mu, la = mu_0 * h, lambda_0 * h
    if material[p] == 0: # liquid
      mu = 0.0
    U, sig, V = ti.svd(F[p])
    J = 1.0
    for d in ti.static(range(2)):
      new_sig = sig[d, d]
      # if material[p] == 2:  # Snow
      #   new_sig = min(max(sig[d, d], 1 - 2.5e-2), 1 + 4.5e-3)  # Plasticity
      Jp[p] *= sig[d, d] / new_sig
      sig[d, d] = new_sig
      J *= new_sig
    if material[p] == 0:  # Reset deformation gradient to avoid numerical instability
      F[p] = ti.Matrix.identity(float, 2) * ti.sqrt(J)
    # elif material[p] == 2:
    #   F[p] = U @ sig @ V.transpose() # Reconstruct elastic deformation gradient after plasticity
    stress = ti.Matrix.identity(float, 2) * la * J * (J - 1)
    stress = (-dt * p_vol * 3 * inv_dx * inv_dx) * stress
    affine = stress + p_mass * C[p]
    for i, j in ti.static(ti.ndrange(4, 4)): # Loop over 4x4 grid node neighborhood
      offset = ti.Vector([i, j]) - 1
      dpos = (offset.cast(float) - fx) * dx
      weight = w[i][0] * w[j][1]
      grid_v[base + offset] += weight * (p_mass * v[p] + affine @ dpos)
      grid_m[base + offset] += weight * p_mass
  for i, j in grid_m:
    if grid_m[i, j] > 0: # No need for epsilon here
      grid_v[i, j] = (1 / grid_m[i, j]) * grid_v[i, j] # Momentum to velocity
      grid_v[i, j][1] -= dt * 50 # gravity
      if i < 3 and grid_v[i, j][0] < 0: grid_v[i, j][0] = 0 # Boundary conditions
      if i > n_grid - 3 and grid_v[i, j][0] > 0: grid_v[i, j][0] = 0
      if j < 3 and grid_v[i, j][1] < 0: grid_v[i, j][1] = 0
      if j > n_grid - 3 and grid_v[i, j][1] > 0: grid_v[i, j][1] = 0
  for p in x: # grid to particle (G2P)

    base = (x[p] * inv_dx).cast(int)
    fx = x[p] * inv_dx - base.cast(float)
    w = [1./6.*(2. - (fx + 1))**3, 0.5*fx**3 - fx**2 + 2./3., 0.5*(-(fx - 1.))**3 - (-(fx - 1.))**2 + 2./3., 1./6.*(2. + (fx - 2.))**3]
    new_v = ti.Vector.zero(float, 2)
    new_C = ti.Matrix.zero(float, 2, 2)
    for i, j in ti.static(ti.ndrange(4, 4)): # loop over 4x4 grid node neighborhood
      dpos = ti.Vector([i, j]).cast(float) - fx - 1
      g_v = grid_v[base + ti.Vector([i, j]) - 1]
      weight = w[i][0] * w[j][1]
      new_v += weight * g_v
      new_C += 3 * inv_dx * weight * g_v.outer_product(dpos)
    v[p], C[p] = new_v, new_C
    x[p] += dt * v[p] # advection

group_size = n_particles // 3
@ti.kernel
def initialize():
  for i in range(n_particles):
    x[i] = [ti.random() * 0.2 + 0.3 + 0.10 * (i // group_size), ti.random() * 0.2 + 0.05 + 0.32 * (i // group_size)]
    material[i] = 1 // group_size # 0: fluid 1: jelly 2: snow
    v[i] = ti.Matrix([0, 0])
    F[i] = ti.Matrix([[1, 0], [0, 1]])
    Jp[i] = 1

initialize()

gui = ti.GUI("Taichi MLS-MPM-99", res=512, background_color=0x112F41)
while not gui.get_event(ti.GUI.ESCAPE, ti.GUI.EXIT):
  for s in range(int(2e-3 // dt)):
    substep()
  colors = np.array([0x068587, 0xED553B, 0xEEEEF0], dtype=np.uint32)
  gui.circles(x.to_numpy(), radius=1.5, color=colors[material.to_numpy()])
  gui.show() # Change to gui.show(f'{frame:06d}.png') to write images to disk