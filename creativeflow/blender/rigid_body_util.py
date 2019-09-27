"""
Utilities for animating ShapeNet using blender's rigid body simulator. Relies on Blender 2.79 built in API.
"""
import bpy
import random
import math
import numpy as np

import geo_util


def set_random_physical_properties(objects):
    """ Set random physical properties for the object. """
    if len(objects) == 0:
        return

    friction = random.uniform(0.4, 0.96)
    restitution = random.uniform(0.01, 0.45)

    for obj in objects:
        obj.rigid_body.friction = friction
        obj.rigid_body.restitution = restitution
        obj.rigid_body.use_margin = True
        obj.rigid_body.mass = random.uniform(0.5, 7.0)

    if len(objects) == 1:
        objects[0].rotation_euler[2] = random.uniform(0, math.pi * 2)


def set_kinematic_initial_conditions(objects):
    """
    Set kinematic initial conditions, such as angular momentum and initial
    velocity. Note that this cannot be done directly, and instead we manually
    animate the object from keyframes 1..10, at which point the rigid body
    simulator takes over using the physical properties calculated from keyframe
    based animation.
    """
    # Add angular momentum
    if len(objects) == 1:
        do_rotate = random.random() > 0.6
        if do_rotate:
            idx = random.randint(0, 1)
            objects[0].rotation_euler[idx] = 0
            objects[0].keyframe_insert("rotation_euler", frame=1)
            objects[0].rotation_euler[idx] = random.uniform(0, math.pi * 2)
            objects[0].keyframe_insert("rotation_euler", frame=10)

    # Compute initial object trajectory and offsets common for all passed in objects
    target = np.array([ random.uniform(-0.5, 0.5), random.uniform(-0.2, -0.2), 0 ])
    offset_dir = np.array([ random.uniform(-1.0, 1.0),
                            random.uniform(-1.0, 1.0),
                            random.uniform(0.2, 1) ])
    offset_dir = offset_dir / np.linalg.norm(offset_dir)
    close_offset = random.uniform(1.0, 4.0)
    far_offset = close_offset + random.uniform(1.0, 20.0)

    close_location = target + offset_dir * close_offset
    far_location = target + offset_dir * far_offset
    print('Close location: %s' % str(close_location))
    print('Far location: %s' % str(far_location))

    for obj in objects:
        orig_location = np.array([obj.location[0], obj.location[1], obj.location[2] ])

        for i in range(3):
            obj.location[i] = orig_location[i] + far_location[i]
        obj.keyframe_insert("location", frame=1)

        for i in range(3):
            obj.location[i] = orig_location[i] + close_location[i]
        obj.keyframe_insert("location", frame=10)

        obj.rigid_body.kinematic = True
        obj.keyframe_insert("rigid_body.kinematic", frame=1)
        obj.rigid_body.kinematic = True
        obj.keyframe_insert("rigid_body.kinematic", frame=10)
        obj.rigid_body.kinematic = False
        obj.keyframe_insert("rigid_body.kinematic", frame=11)
        obj.rigid_body.kinematic = False
        obj.keyframe_insert("rigid_body.kinematic", frame=250)

    # for fc in obj.animation_data.action.fcurves:
    #    fc.extrapolation = 'LINEAR'


def animate_objects(objs):
    """
    Set up rigid objects with initial conditions, corresponding to the passed
    in objects.
    """
    for obj in objs:
        bpy.ops.object.select_all(action='DESELECT')
        obj.select = True
        bpy.context.scene.objects.active = obj

        bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY')
        bpy.ops.rigidbody.object_add()

    set_random_physical_properties(objs)
    set_kinematic_initial_conditions(objs)


def make_keyframe_context():
    """
    For reasons unknown, baking a simulation to keyframes requires values for
    screen areas to be set in the context; which is not the case when the
    script is run in background mode.
    """
    # https://developer.blender.org/diffusion/B/browse/master/source/blender/editors/animation/keyframing.c
    print('Area')
    print(bpy.context.area)
    if bpy.context.area:
        print('Area type %s' % str(bpy.context.area.type))
    print('Scene')
    print(bpy.context.scene)

    override = bpy.context.copy()
    if not bpy.context.area:
        for window in bpy.context.window_manager.windows:
            screen = window.screen

            for area in screen.areas:
                if area.type == 'VIEW_3D':
                    override['area'] = area
                    override['window'] = window
                    override['screen'] = screen
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            override['region'] = region
                            break
                    for space in area.spaces:
                        if space.type == 'VIEW_3D':
                            override['space_data'] = space
    return override


def bake_simulation():
    """
    Note: this only works if invoked from python console; not in background mode --
    unclear what is wrong with the context.
    """
    print('Baking objects')
    geo_util.ensure_object_mode()

    for obj in bpy.context.scene.objects:
        if obj.rigid_body is not None and obj.rigid_body.type != 'PASSIVE':
            print('Baking object %s' % obj.name)
            bpy.ops.object.select_all(action='DESELECT')
            obj.select = True
            bpy.context.scene.objects.active = obj

            override = make_keyframe_context()
            print('Override')
            print(override)

            bpy.ops.rigidbody.bake_to_keyframes(override)


def bake_simulation_bugfix(frame_start=None, frame_end=None, step=1):
    """
    Note, technically bake_simulation above should work, and it does, when invoked
    from py console in GUI. However, when run in background mode, parts of the context
    must be overrideen, and there is a bug in blender, where the context passed
    in to bpy.ops.rigidbody.bake_to_keyframes is not passed on to bpy.ops.anim.keyframe_insert.
    To ensure that our scripts run on standard versions of Blender, we lift
    this function almost unchanged from:
    https://developer.blender.org/diffusion/B/browse/master/release/scripts/startup/bl_operators/rigidbody.py;9bdda427e6ffa2b07f924530b7d2a2db6adbb797
    and fix the bug.
    """
    geo_util.ensure_object_mode()
    bpy.ops.object.select_all(action='SELECT')
    scene = bpy.context.scene

    if not frame_start:
        frame_start = scene.frame_start
    if not frame_end:
        frame_end = scene.frame_end

    override = make_keyframe_context()

    bake = []
    frame_orig = scene.frame_current
    frames_step = range(frame_start, frame_end + 1, step)
    frames_full = range(frame_start, frame_end + 1)

    # filter objects selection
    for obj in bpy.context.selected_objects:
        if not obj.rigid_body or obj.rigid_body.type != 'ACTIVE':
            obj.select = False

    objects = bpy.context.selected_objects

    if objects:
        # store transformation data
        # need to start at scene start frame so simulation is run from the beginning
        for f in frames_full:
            scene.frame_set(f)
            if f in frames_step:
                mat = {}
                for i, obj in enumerate(objects):
                    mat[i] = obj.matrix_world.copy()
                bake.append(mat)

        # apply transformations as keyframes
        for i, f in enumerate(frames_step):
            scene.frame_set(f)
            for j, obj in enumerate(objects):
                mat = bake[i][j]
                # convert world space transform to parent space, so parented objects don't get offset after baking
                if obj.parent:
                    mat = obj.matrix_parent_inverse.inverted() * obj.parent.matrix_world.inverted() * mat

                obj.location = mat.to_translation()

                rot_mode = obj.rotation_mode
                if rot_mode == 'QUATERNION':
                    q1 = obj.rotation_quaternion
                    q2 = mat.to_quaternion()
                    # make quaternion compatible with the previous one
                    if q1.dot(q2) < 0.0:
                        obj.rotation_quaternion = -q2
                    else:
                        obj.rotation_quaternion = q2
                elif rot_mode == 'AXIS_ANGLE':
                    # this is a little roundabout but there's no better way right now
                    aa = mat.to_quaternion().to_axis_angle()
                    obj.rotation_axis_angle = (aa[1], *aa[0])
                else:  # euler
                    # make sure euler rotation is compatible to previous frame
                    # NOTE: assume that on first frame, the starting rotation is appropriate
                    obj.rotation_euler = mat.to_euler(rot_mode, obj.rotation_euler)

            bpy.ops.anim.keyframe_insert(override, type='BUILTIN_KSI_LocRot', confirm_success=False)

        # remove baked objects from simulation
        bpy.ops.rigidbody.objects_remove()

        # clean up keyframes
        for obj in objects:
            action = obj.animation_data.action
            for fcu in action.fcurves:
                keyframe_points = fcu.keyframe_points
                i = 1
                # remove unneeded keyframes
                while i < len(keyframe_points) - 1:
                    val_prev = keyframe_points[i - 1].co[1]
                    val_next = keyframe_points[i + 1].co[1]
                    val = keyframe_points[i].co[1]

                    if abs(val - val_prev) + abs(val - val_next) < 0.0001:
                        keyframe_points.remove(keyframe_points[i])
                    else:
                        i += 1
                # use linear interpolation for better visual results
                for keyframe in keyframe_points:
                    keyframe.interpolation = 'LINEAR'

        # return to the frame we started on
        scene.frame_set(frame_orig)

    return {'FINISHED'}


def bake_simulation_transforms_only():
    """
    This versions can be used to access object transforms post simulation, but
    it does not convert simulation to keyframes.
    """
    override = {'scene': bpy.context.scene,
                'point_cache': bpy.context.scene.rigidbody_world.point_cache}
    # bake to current frame
    bpy.ops.ptcache.bake(override, bake=False)


def create_floor():
    """
    Creates a large passive rigid body floor.
    """
    bpy.ops.mesh.primitive_cube_add(radius=0.05)
    bpy.ops.object.align(align_mode='OPT_3', relative_to='OPT_2', align_axis={'Z'})
    floor = bpy.context.object
    floor.scale[0] = 100
    floor.scale[1] = 100

    # Add a corresponding rigid body
    bpy.ops.rigidbody.object_add()
    bpy.context.object.rigid_body.type = 'PASSIVE'
    set_random_physical_properties([floor])

    return floor


def obj_import(obj_file, do_join_objects=False, do_fix_normals=False):
    """
    Imports OBJ; joins all objects into one if requested; fixes normals if
    requested (this is far from foolproof). Returns the list of objects
    that correspond to imported objects.
    """
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.import_scene.obj(filepath=obj_file)
    activeObjects = bpy.context.selected_objects
    if len(activeObjects) == 0:
        raise RuntimeError('No objects found in %s' % obj_file)

    # Join objects to prevent breaking
    if do_join_objects:
        bpy.context.scene.objects.active = activeObjects[0]
        bpy.ops.object.join()
        activeObjects = bpy.context.selected_objects

    if do_fix_normals:
        geo_util.fix_normals(activeObjects)

    for mat in bpy.data.materials:
        mat.ambient = 1

    bpy.ops.object.select_all(action='DESELECT')
    return activeObjects


def obj_import_diagnostic(obj_file):
    """
    Import without animating; for diagnostic purposes only
    """
    bpy.context.scene.cursor_location = (0, 0, 0)
    geo_util.delete_all_objects()

    # Import obj file ----------------------------------------------------------
    activeObjects = obj_import(obj_file, do_fix_normals=True)

    bbox = geo_util.get_scene_bbox()
    print('Bounding box: %s' % str(bbox))


def set_rigidbody_world_properties(steps_per_sec=120, time_scale=1.0, solver_its=10):
    """
    Set global rigid body simulation properties.
    """
    bpy.context.scene.rigidbody_world.steps_per_second = steps_per_sec
    bpy.context.scene.rigidbody_world.time_scale = time_scale
    bpy.context.scene.rigidbody_world.solver_iterations = solver_its


def obj_import_animate(obj_file, allow_breaking=False, bg_name='STYMO_BG'):
    bpy.context.scene.cursor_location = (0, 0, 0)
    geo_util.delete_all_objects()

    # Import obj file ----------------------------------------------------------
    activeObjects = obj_import(obj_file,
                               do_join_objects=(not allow_breaking),
                               do_fix_normals=True)

    # Create floor -------------------------------------------------------------
    floor = create_floor()
    floor.name = bg_name

    # Create rigid body simulation ---------------------------------------------
    set_rigidbody_world_properties()
    animate_objects(activeObjects)

    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 100
    bpy.context.scene.frame_set(1)

    return floor, activeObjects
