import taichi as ti
import json

from Scenes import concat_test as scene1
import os
from framework.physics import XPBD
from framework.utilities import selection_tool as st

sim = XPBD.Solver(scene1.obj_mesh_dy, scene1.obj_mesh_st, g=ti.math.vec3(0.0, -7., 0.0), dt=0.03, stiffness_stretch=5e5, stiffness_bending=5e5, dHat=4e-3)
window = ti.ui.Window("PBD framework", (1024, 768), fps_limit=200)
gui = window.get_gui()
canvas = window.get_canvas()
canvas.set_background_color((1, 1, 1))
scene = window.get_scene()
camera = ti.ui.Camera()
camera.position(2., 4.0, 7.0)
camera.fov(40)
camera.up(0, 1, 0)

run_sim = False
MODE_WIREFRAME = False
LOOKAt_ORIGIN = True
#selector
g_selector = st.SelectionTool(sim.num_verts_dy, sim.mesh_dy.x, window, camera)

n_substep = 20
frame_end = 100

dt_ui = sim.dt
solver_type_ui = sim.selected_solver_type
dHat_ui = sim.dHat

damping_ui = sim.damping

YM_b_ui = sim.stiffness_bending
YM_ui = sim.stiffness_stretch

friction_coeff_ui = sim.mu

mesh_export = False
frame_cpu = 0

def show_options():

    global n_substep
    global dt_ui
    global solver_type_ui
    global damping_ui
    global YM_ui
    global YM_b_ui
    global sim
    global dHat_ui
    global friction_coeff_ui
    global MODE_WIREFRAME
    global LOOKAt_ORIGIN
    global mesh_export
    global frame_end

    old_dt = dt_ui
    old_solver_type_ui = solver_type_ui
    old_dHat = dHat_ui
    old_friction_coeff = dHat_ui
    old_damping = damping_ui
    YM_old = YM_ui
    YM_b_old = YM_b_ui

    with gui.sub_window("XPBD Settings", 0., 0., 0.3, 0.7) as w:
        solver_type_ui = w.slider_int("solver type", solver_type_ui, 0, 4)
        if solver_type_ui == 0:
            w.text("solver type: Jacobi")
        elif solver_type_ui == 1:
            w.text("solver type: Gauss Seidel")
        elif solver_type_ui == 2:
            w.text("solver type: Parallel Gauss Seidel")
        elif solver_type_ui == 3:
            w.text("solver type: Euler Path")
        elif solver_type_ui == 4:
            w.text("solver type: Tridiagonal Euler Path")

        dt_ui = w.slider_float("dt", dt_ui, 0.001, 0.101)
        n_substep = w.slider_int("# sub", n_substep, 1, 100)
        dHat_ui = w.slider_float("dHat", dHat_ui, 0.0001, 0.0301)
        friction_coeff_ui = w.slider_float("fric. coef.", friction_coeff_ui, 0.0, 1.0)
        damping_ui = w.slider_float("damping", damping_ui, 0.0, 1.0)
        YM_ui = w.slider_float("stretch stiff.", YM_ui, 0.0, 1e8)
        YM_b_ui = w.slider_float("bending stiff.", YM_b_ui, 0.0, 1e8)

        frame_str = "# frame: " + str(frame_cpu)
        w.text(frame_str)

        LOOKAt_ORIGIN = w.checkbox("Look at origin", LOOKAt_ORIGIN)
        # sim.enable_velocity_update = w.checkbox("velocity constraint", sim.enable_velocity_update)
        # sim.enable_collision_handling = w.checkbox("handle collisions", sim.enable_collision_handling)
        # mesh_export = w.checkbox("export mesh", mesh_export)

        if mesh_export is True:
            frame_end = w.slider_int("end frame", frame_end, 1, 2000)

        w.text("")
        w.text("dynamic mesh stats.")
        verts_str = "# verts: " + str(sim.num_verts_dy)
        edges_str = "# edges: " + str(sim.num_edges_dy)
        faces_str = "# faces: " + str(sim.num_faces_dy)
        w.text(verts_str)
        w.text(edges_str)
        w.text(faces_str)
        w.text("")
        w.text("static mesh stats.")
        verts_str = "# verts: " + str(sim.num_verts_st)
        edges_str = "# edges: " + str(sim.num_edges_st)
        faces_str = "# faces: " + str(sim.num_faces_st)
        w.text(verts_str)
        w.text(edges_str)
        w.text(faces_str)

    if not old_dt == dt_ui:
        sim.dt = dt_ui

    if not old_solver_type_ui == solver_type_ui:
        sim.selected_solver_type = solver_type_ui

    if not old_dHat == dHat_ui:
        sim.dHat = dHat_ui

    if not old_friction_coeff == friction_coeff_ui:
        sim.mu = friction_coeff_ui

    if not YM_old == YM_b_ui:
        sim.stiffness_bending = YM_b_ui

    if not YM_b_old == YM_ui:
        sim.stiffness_stretch = YM_ui

    if not old_damping == damping_ui:
        sim.damping = damping_ui

def load_animation():
    global sim

    with open('framework/animation/animation.json') as f:
        animation_raw = json.load(f)
    animation_raw = {int(k): v for k, v in animation_raw.items()}

    animationDict = {(i+1):[] for i in range(4)}

    for i in range(4):
        ic = i + 1
        icAnimation = animation_raw[ic]
        listLen = len(icAnimation)
        # print(listLen)
        assert listLen % 7 == 0,str(ic)+"th Animation SETTING ERROR!! ======"

        num_animation = listLen // 7

        for a in range(num_animation) :
            animationFrag = [animation_raw[ic][k + 7*a] for k in range(7)] # [vx,vy,vz,rx,ry,rz,frame]
            animationDict[ic].append(animationFrag)

while window.running:

    if LOOKAt_ORIGIN:
        camera.lookat(0.0, 0.0, 0.0)

    scene.set_camera(camera)
    scene.ambient_light((0.5, 0.5, 0.5))
    scene.point_light(pos=(0.5, 1.5, 0.5), color=(0.3, 0.3, 0.3))
    scene.point_light(pos=(0.5, 1.5, 1.5), color=(0.3, 0.3, 0.3))

    if window.get_event(ti.ui.PRESS):

        if window.event.key == 'x':  # export selection
            print("==== Vertex EXPORT!! ====")
            g_selector.export_selection()

        if window.event.key == 'i':
            print("==== IMPORT!! ====")
            g_selector.import_selection()
            sim.set_fixed_vertices(g_selector.is_selected)
            # load_animation()

        if window.event.key == 't':
            g_selector.sewing_selection()

        if window.event.key == 'y':
            g_selector.pop_sewing()

        # if window.event.key == 'u':
        #     g_selector.remove_all_sewing()


        if window.event.key == ' ':
            run_sim = not run_sim

        if window.event.key == 'r':
            frame_cpu = 0
            sim.reset()
            g_selector.is_selected.fill(0.0)
            sim.set_fixed_vertices(g_selector.is_selected)
            run_sim = False

        if window.event.key == 'v':
            sim.enable_velocity_update = not sim.enable_velocity_update
            if sim.enable_velocity_update is True:
                print("velocity update on")
            else:
                print("velocity update off")

        if window.event.key == 'z':
            sim.enable_collision_handling = not sim.enable_collision_handling
            if sim.enable_collision_handling is True:
                print("collision handling on")
            else:
                print("collision handling off")

        if window.event.key == 'h':
            print("fix vertices")
            sim.set_fixed_vertices(g_selector.is_selected)

        if window.event.key == ti.ui.BACKSPACE:
            g_selector.is_selected.fill(0)

        if window.event.key == ti.ui.LMB:
            g_selector.LMB_mouse_pressed = True
            g_selector.mouse_click_pos[0], g_selector.mouse_click_pos[1] = window.get_cursor_pos()

        if window.event.key == ti.ui.TAB:
            g_selector.MODE_SELECTION = not g_selector.MODE_SELECTION


    if window.get_event(ti.ui.RELEASE):
        if window.event.key == ti.ui.LMB:
            g_selector.LMB_mouse_pressed = False
            g_selector.mouse_click_pos[2], g_selector.mouse_click_pos[3] = window.get_cursor_pos()
            g_selector.Select()

    if g_selector.LMB_mouse_pressed:
        g_selector.mouse_click_pos[2], g_selector.mouse_click_pos[3] = window.get_cursor_pos()
        g_selector.update_ti_rect_selection()

    if run_sim:
        # sim.animate_handle(g_selector.is_selected)
        sim.forward(n_substeps=n_substep)
        frame_cpu += 1

    show_options()

    if mesh_export and run_sim and frame_cpu < frame_end:
        sim.mesh_dy.export(os.path.basename(scene1.__file__), frame_cpu)

    scene.mesh(sim.mesh_dy.x, indices=sim.mesh_dy.face_indices_flatten, per_vertex_color=sim.mesh_dy.colors)
    scene.mesh(sim.mesh_dy.x, indices=sim.mesh_dy.face_indices_flatten, color=(0, 0.0, 0.0), show_wireframe=True)

    # scene.lines(sim.mesh_dy.x_euler, indices=sim.mesh_dy.edge_indices_euler, width=1.0, color=(0., 0., 0.))
    # scene.particles(sim.mesh_dy.x_euler, radius=0.02, color=(0., 0., 0.))
    # sim.mesh_dy.colors_edge_euler.fill(ti.math.vec3([1.0, 0.0, 0.0]))
    scene.particles(sim.mesh_dy.colored_edge_pos_euler, radius=0.05,  per_vertex_color=sim.mesh_dy.edge_color_euler)
    # if sim.mesh_st != None:
    #     scene.mesh(sim.mesh_st.x, indices=sim.mesh_st.face_indices_flatten, color=(0, 0.0, 0.0), show_wireframe=True)
    #     scene.mesh(sim.mesh_st.x, indices=sim.mesh_st.face_indices_flatten, per_vertex_color=sim.mesh_st.colors)

    g_selector.renderTestPos()

    #draw selected particles
    scene.particles(g_selector.renderTestPosition, radius=0.02, color=(1, 0, 1))
    canvas.lines(g_selector.ti_mouse_click_pos, width=0.002, indices=g_selector.ti_mouse_click_index, color=(1, 0, 1) if g_selector.MODE_SELECTION else (0, 0, 1))

    camera.track_user_inputs(window, movement_speed=0.8, hold_key=ti.ui.RMB)
    canvas.scene(scene)
    window.show()