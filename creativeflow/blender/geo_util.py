"""
Geometry/camera related utilities, mostly containing blender-specific code that relies on Blender 2.79 built-in API
(bpy, bpy_extras and mathutils packages).
"""
import bpy
import bpy_extras
import random
import math
import numpy as np
import itertools
import time
from mathutils import Vector


class BBox:
    """
    Convenience bounding box representation.
    """


    def __init__(self, mins, maxs):
        self.mins = mins
        self.maxs = maxs


    def get_center(self):
        return list(map(lambda mx, mi: (mx + mi) / 2.0, self.maxs, self.mins))


    def get_dims(self):
        return list(map(lambda mx, mi: mx - mi, self.maxs, self.mins))


    def expand_to_contain(self, coord):
        self.mins = list(map(lambda curr, co: min(curr, co), self.mins, coord))
        self.maxs = list(map(lambda curr, co: max(curr, co), self.maxs, coord))


    def get_points(self):
        temp = list(map(lambda mx, mi: [mx, mi], self.maxs, self.mins))
        return list(itertools.product(*temp))


    def merge_with(self, bbox):
        self.expand_to_contain(bbox.mins)
        self.expand_to_contain(bbox.maxs)


    def __str__(self):
        return ('%s @ (%s)' %
                (' x '.join([('%0.3f' % (self.maxs[i] - self.mins[i])) for i in range(len(self.maxs))]),
                 ', '.join([('%0.3f' % x) for x in self.get_center()])))


def ensure_object_mode():
    ensure_blender_mode('OBJECT')


def ensure_blender_mode(bmode):
    if bpy.context.mode != bmode:
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode=bmode)
        else:
            raise RuntimeError('Cannot set mode to %s; current mode %s' %
                               (bmode, bpy.context.mode))


def delete_all_cameras():
    """ Delete all cameras. """
    delete_all_objects_of_type('CAMERA')


def delete_all_objects_of_type(typename):
    """ Delete all objects of a specific blender type. """
    ensure_object_mode()

    scene = bpy.context.scene
    selected = False

    for ob in scene.objects:
        if ob.type == typename:
            selected = True
            ob.select = True
        else:
            ob.select = False
    if selected:
        bpy.ops.object.delete()


def delete_all_objects():
    """ Delete all objects. """
    ensure_object_mode()

    scene = bpy.context.scene
    if len(scene.objects) > 0:
        for ob in scene.objects:
            ob.select = True
    bpy.ops.object.delete()


def fix_normals(objs):
    """
    Fixes normals using built-in blender utilities; hard cases are generally
    not handled, and lots of ShapeNet models have problems.
    """
    ensure_object_mode()
    for obj in objs:
        bpy.ops.object.select_all(action='DESELECT')
        obj.select = True
        bpy.context.scene.objects.active = obj

        obj.data.show_double_sided = True
        bpy.ops.mesh.customdata_custom_splitnormals_clear()  # Fixes the normal artifacts
        ensure_blender_mode('EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.normals_make_consistent()
        ensure_object_mode()


def deselect_all_objects():
    scene = bpy.context.scene
    for ob in scene.objects:
        ob.select = False


def delete_all_but_one_camera(keep_camera_number=0):
    """
    Will delete all cameras except for one if cameras exist in the scene.
    """
    ensure_object_mode()

    scene = bpy.context.scene
    nselected = 0

    cam_num = 0
    cam = None
    for ob in scene.objects:
        if ob.type == 'CAMERA':
            if cam_num == keep_camera_number:
                ob.select = False
                cam = ob
            else:
                ob.select = True
                nselected += 1
            cam_num += 1
        else:
            ob.select = False

    if nselected > 0:
        print('Deleting %d cameras' % nselected)
        bpy.ops.object.delete()

    return cam


def get_camera_by_number(camera_number):
    scene = bpy.context.scene

    cam_num = 0
    for ob in scene.objects:
        if ob.type == 'CAMERA':
            if cam_num == camera_number:
                return ob
            cam_num += 1
    return None


def get_obj_bbox(obj, obj_space=False):
    """
    Gets the bounding box for a single object.

    Input:
    obj - of type bpy_types.Object

    Output:
    bbox - A BBox object
    """
    mins = []
    maxs = []

    if obj_space:
        bbox = [Vector(b) for b in obj.bound_box]
    else:
        mat = obj.matrix_world
        bbox = [mat * Vector(b) for b in obj.bound_box]

    mins.append(min(b.x for b in bbox))
    maxs.append(max(b.x for b in bbox))
    mins.append(min(b.y for b in bbox))
    maxs.append(max(b.y for b in bbox))
    mins.append(min(b.z for b in bbox))
    maxs.append(max(b.z for b in bbox))
    bbox = BBox(mins, maxs)
    return bbox


def get_scene_bbox():
    """
    Gets the bounding box for objects in the scene.
    Note: may need to disregard outliers like the floor - TBD.

    Output:
    bbox - A BBox object
    """
    mins = [float("inf"), float("inf"), float("inf")]

    maxs = [float("-inf"), float("-inf"), float("-inf")]

    # Deselect all objects
    for ob in bpy.context.selected_objects:
        ob.select = False

    # Get all mesh names
    mesh_names = [v for v in bpy.context.scene.objects if v.type == 'MESH']

    for j in range(0, len(mesh_names)):
        ob = mesh_names[j]
        cube = get_obj_bbox(ob)
        for i in range(3):
            mins[i] = cube.mins[i] if cube.mins[i] < mins[i] else mins[i]
            maxs[i] = cube.maxs[i] if cube.maxs[i] > maxs[i] else maxs[i]

    # Create bounding box representation
    bbox = BBox(mins, maxs)
    return bbox


def distance_from_camera_center(bbox, cam):
    """ Returns distance from image plane center """
    scene = bpy.context.scene
    center = bbox.get_center()
    center = Vector((center[0], center[1], center[2]))
    cam_cood = bpy_extras.object_utils.world_to_camera_view(scene, cam, center)
    return (cam_cood[0] - 0.5) ** 2 + (cam_cood[1] - 0.5) ** 2


def get_scene_bbox_animated():
    """ Return bounding box for mesh objects in the scene across all frames. """
    scene = bpy.context.scene

    scene.frame_set(scene.frame_start)
    bbox = get_scene_bbox()
    for i in range(scene.frame_start + 1, scene.frame_end):
        scene.frame_set(i)
        bbox.merge_with(get_scene_bbox())
    return bbox


def camera_point_at(cam, pt):
    """ Rotates the camera to look at pt. """
    ray = cam.location - pt
    quat = ray.to_track_quat('Z', 'Y')
    cam.rotation_euler = quat.to_euler()


def switch_to_camera_by_number(num):
    cam = get_camera_by_number(num)
    switch_to_camera(cam)


def switch_to_camera(cam):
    deselect_all_objects()
    cam.select = True

    bpy.context.scene.objects.active = cam
    bpy.context.scene.camera = cam
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces.active.region_3d.view_perspective = 'CAMERA'
            override = bpy.context.copy()
            override['area'] = area
            bpy.ops.view3d.object_as_camera(override)
        break


def play_animation_on_camera_by_number(num):
    switch_to_camera_by_number(num)
    bpy.context.scene.frame_set(bpy.context.scene.frame_start)
    bpy.ops.screen.animation_play()


def generate_random_cameras_for_scene(ncam):
    """ Updated random camera generator designed for creating a large
    number of camera angles for an animated scene.
    Camera is always fixed and uses orthographic projection.
    """
    # Compute bounding box for the entire animated scene
    bbox = get_scene_bbox_animated()
    bbox_dims = bbox.get_dims()
    bbox_center = bbox.get_center()

    # Sample the top and bottom less densely
    ncam_tb = int(ncam * 0.2)
    ncam_sides = ncam - ncam_tb
    if (ncam_sides % 2) == 1:
        ncam_tb = ncam_tb - 1
        ncam_sides = ncam - ncam_tb
    ncam_top = ncam_tb // 2
    ncam_bottom = ncam_tb - ncam_top

    # Sample the sides of the box proportional to their area
    ncam_sides_half = ncam_sides // 2
    area_xz = bbox_dims[0] * bbox_dims[2]
    area_yz = bbox_dims[1] * bbox_dims[2]
    ncam_xz_half = int(ncam_sides_half * area_xz / (area_xz + area_yz))
    ncam_yz_half = ncam_sides_half - ncam_xz_half

    # Generate side cameras
    for side in ['xz', 'yz']:
        for c in range(ncam_xz_half if side == 'xz' else ncam_yz_half):
            for other_mult in [-1, 1]:
                z = random.random() * bbox_dims[2] + bbox.mins[2]

                if side == 'xz':
                    x = random.random() * bbox_dims[0] + bbox.mins[0]
                    y = bbox.mins[1] if other_mult == -1 else bbox.maxs[1]
                else:
                    y = random.random() * bbox_dims[1] + bbox.mins[1]
                    x = bbox.mins[0] if other_mult == -1 else bbox.maxs[0]


                # Note: for orthographic cameras rotation jittering forward/back
                # has no effect. Instead we jitter the scaling.
                bpy.ops.object.camera_add(location=Vector((x, y, z)))
                cam = bpy.context.object
                cam.data.type = 'ORTHO'
                cam.data.clip_start = 0
                cam.data.ortho_scale = random.random() * 9 + 1.0

                # 50% of cameras just point straight
                is_straight = random.random() < 0.5
                if is_straight:
                    look_at = Vector((x if side == 'xz' else bbox_center[0],
                                      y if side == 'yz' else bbox_center[1],
                                      z))
                else:
                    look_at = Vector((bbox_center[0] + np.random.normal(scale=0.2*bbox_dims[0]),
                                      bbox_center[1] + np.random.normal(scale=0.2*bbox_dims[1]),
                                      bbox_center[2] + np.random.normal(scale=0.2*bbox_dims[2])))
                    camera_point_at(cam, look_at)


    # 50% of side cameras point straight

    # all of top/bottom cameras point at character in one of the frames



def create_random_camera(bbox, frac_space_x, frac_space_y, frac_space_z):
    """ Creates a new camera, sets a random position for it, for a scene inside the bbox.
    Given the same random_seed the pose of the camera is deterministic.

    Input:
    bbox - same rep as output from get_scene_bbos.

    Output:
    new camera created
    """
    rand_theta = random.uniform(0, 2 * math.pi)  # Rotate around z
    # Phi: 0 - top view, 0.5 * pi - side view, -pi - bottom view
    rand_sign = random.randint(0, 1) * 2 - 1.0
    rand_phi = rand_sign * random.normalvariate(0.4, 0.2) * math.pi
    max_dim = max(bbox.get_dims())
    r = random.uniform(max_dim * 0.4, max_dim * 0.6)

    x = frac_space_x * r * math.cos(rand_theta) * math.sin(rand_phi) + bbox.get_center()[0]
    y = frac_space_y * r * math.sin(rand_theta) * math.sin(rand_phi) + bbox.get_center()[1]
    z = frac_space_z * r * math.cos(rand_phi) + bbox.get_center()[2]

    bpy.ops.object.camera_add(location=Vector((x, y, z)))
    cam = bpy.context.object
    cam.data.clip_start = 0.01
    cam.data.clip_end = max(170, r * 2 * 10)
    look_at(cam, Vector(bbox.get_center()))
    return cam


def disable_camera_depth_of_field(cam):
    """
    Input is bpy_types.Object; cam.data should be bpy.types.Camera
    """
    cam.data.gpu_dof.fstop = 10000
    cam.data.cycles.aperture_size = 0.0
    cam.data.dof_distance = 0.0


def look_at(camera, point):
    """
    Takes a camera and a point in the world. Will rotate the camera to face
    the point.

    Input:
    camera - a camera object
    point - a vector location
    """
    camera_loc = camera.matrix_world.to_translation()

    direction = point - camera_loc
    rot_quat = direction.to_track_quat('-Z', 'Y')

    camera.rotation_euler = rot_quat.to_euler()


def get_single_camera_or_die():
    """
    Returns a single camera present in the scene (such as the one created
    by create_random_camera). Raises an exception if more than one or no camera
    found.

    Output:
    found camera
    """
    scene = bpy.context.scene
    camera = None
    for ob in scene.objects:
        if ob.type == 'CAMERA':
            if camera is not None:
                raise RuntimeError('More than one camera found')
            camera = ob
    if camera is None:
        raise RuntimeError('No camera found')
    return camera


def save_blend(filename):
    """
    Saves current blend to file.

    Input:
    filename - string, absolute path to blend file
    """
    bpy.ops.wm.save_as_mainfile(filepath=filename)


# Random camera generation for Mixamo Characters ------------------------------

def __find_mixamo_subtargets():
    if 'Armature' not in bpy.data.objects:
        print('No Armature found')
        return []
    armature = bpy.data.objects['Armature']

    keywords = ['Neck', 'Spine', 'Head', 'Hips']
    keywords.extend([x.lower() for x in keywords])
    keywords = set(keywords)

    subtargets = [x for x in armature.pose.bones.keys() if any(k in x for k in keywords)]
    return subtargets


def random_axis():
    vec = np.array([np.random.normal(), np.random.normal(), np.random.normal()])
    vec /= np.linalg.norm(vec)
    return vec


def mixamo_add_random_camera_motion(cam, mo_type=None, add_tracking=True):
    """
    Random camera generation tuned for the blends containing Mixamo character in motion.
    """
    if mo_type is None:
        mo_type = random.randint(0, 2)
        print('Random motion type: %d' % mo_type)

    if mo_type == 0:
        fol_start = random.uniform(20.0, 35.0)
        fol_end = random.uniform(40.0, 75.0)
        fols = [fol_start, fol_end]
        random.shuffle(fols)  # allow zoom in and zoom out
        add_camera_zoom(cam, fols[0], fols[1])
    elif mo_type == 1:
        add_camera_translation(cam, random.uniform(0.5, 2))
    else:
        add_camera_flyaround(cam, random.uniform(1.0, 5.0), random.uniform(1.5, 4.0))

    # Track the moving object
    if add_tracking:
        mixamo_add_camera_tracking(cam)


def mixamo_add_camera_tracking(cam):
    target_obj = bpy.data.objects['Armature']
    subtargets = __find_mixamo_subtargets()
    random.shuffle(subtargets)
    subtarget_obj_name = None
    if len(subtargets) > 0:
        subtarget_obj_name = subtargets[0]
    add_camera_track_constraint(cam, target_obj, subtarget_obj_name)


def add_camera_track_constraint(cam, target_obj, subtarget_obj_name=None):
    ensure_object_mode()
    deselect_all_objects()

    scene = bpy.context.scene
    scene.objects.active = cam
    cam.select = True
    bpy.ops.object.constraint_add(type='TRACK_TO')
    cam.constraints["Track To"].target = target_obj
    if subtarget_obj_name:
        cam.constraints["Track To"].subtarget = subtarget_obj_name
    cam.constraints["Track To"].up_axis = 'UP_Y'
    cam.constraints["Track To"].track_axis = 'TRACK_NEGATIVE_Z'


def add_camera_zoom(cam, fol_start, fol_end):
    scene = bpy.context.scene

    cam.data.lens = fol_start
    cam.data.keyframe_insert("lens", frame=scene.frame_start)
    cam.data.lens = fol_end
    cam.data.keyframe_insert("lens", frame=scene.frame_end)


def add_camera_translation(cam, radius):
    scene = bpy.context.scene

    x = cam.location[0]
    y = cam.location[1]
    z = cam.location[2]

    bpy.ops.curve.primitive_nurbs_path_add(radius=radius, location=(x, y, z))
    # Pose it
    path = bpy.context.object
    direction = Vector((0, 0, z)) - Vector((x, y, z))
    rot_quat = direction.to_track_quat('-Z', 'Y')
    path.rotation_euler = rot_quat.to_euler()

    deselect_all_objects()
    cam.select = True
    path.select = True
    scene.objects.active = path
    bpy.ops.object.parent_set(type='FOLLOW')

    path.data.path_duration = scene.frame_end
    # Hide the curve from the scene
    path.hide = True


def add_camera_flyaround(cam, height, radius):
    # Generate all points data for the curve
    points = [
        [-radius, 0, height], [0, radius, height],
        [radius, 0, height], [0, -radius, height]]
    handle_left = [
        [-radius, -3.31, height], [-3.31, radius, height],
        [radius, 3.31, height], [3.31, -radius, height]]
    handle_right = [
        [-radius, 3.31, height], [3.31, radius, height],
        [radius, -3.31, height], [-3.31, -radius, height]]

    for i in range(len(points)):
        points[i][0] += random.uniform(-1.5, 1.5)
        points[i][1] += random.uniform(-1.5, 1.5)
        points[i][2] += random.uniform(-1.5, 1.5)

        handle_left[i][0] += random.uniform(-1.5, 1.5)
        handle_left[i][1] += random.uniform(-1.5, 1.5)
        handle_left[i][2] += random.uniform(-1.5, 1.5)

        handle_right[i][0] += random.uniform(-1.5, 1.5)
        handle_right[i][1] += random.uniform(-1.5, 1.5)
        handle_right[i][2] += random.uniform(-1.5, 1.5)

    points.append(points[0])
    handle_left.append(handle_left[0])
    handle_right.append(handle_right[0])

    # Generate data block for bezier curve
    curveData = bpy.data.curves.new('CamPath', type='CURVE')
    curveData.dimensions = '3D'
    spline = curveData.splines.new('BEZIER')
    spline.bezier_points.add(len(points) - 1)
    for i in range(len(points)):
        spline.bezier_points[i].co = Vector(points[i])
        spline.bezier_points[i].handle_left = Vector(handle_left[i])
        spline.bezier_points[i].handle_right = Vector(handle_right[i])

    scn = bpy.context.scene
    # Create the curve object
    splineOBJ = bpy.data.objects.new('CamPath', curveData)
    scn.objects.link(splineOBJ)

    # Create Camera
    cam.location = Vector(points[0])

    # Follow the curve
    deselect_all_objects()
    cam.select = True
    splineOBJ.select = True
    scn.objects.active = splineOBJ
    bpy.ops.object.parent_set(type='FOLLOW')

    # Set the frame range of the path identical to the length of the animation\
    splineOBJ.data.path_duration = scn.frame_end
    # Hide the curve from the scene
    splineOBJ.hide = True

    return cam
