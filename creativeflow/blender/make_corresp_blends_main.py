"""
This file is not used in our pipeline. Use this to generate blends from
a collection of STL files for the correspondence task, where only 2 frames
are required.

Sample invocation:
blender --background --python-exit-code 1 --factory-startup \
         --python blender/make_corresp_blends_main.py -- \
         --stl_file=my_object.stl --output_blend=/tmp/out.blend
"""
import argparse
import logging
import math
import numpy as np
import os
import random
import re
import sys

import bpy
from mathutils import Vector

LOG = logging.getLogger(__name__)

# Add to path to make sure we can import modules inside Blender.
__sdir = os.path.dirname(os.path.realpath(__file__))
if __sdir not in sys.path:
    sys.path.append(__sdir)

import geo_util
import render_util


def import_stl(filename):
    bpy.ops.import_mesh.stl(filepath=filename)
    bpy.ops.object.select_all(action='SELECT')
    bpy.context.scene.objects.active = bpy.context.selected_objects[0]
    bpy.ops.object.join()
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY')

    num_objects = len(bpy.context.scene.objects)
    if num_objects != 1:
        raise RuntimeError('Expected one object, but found %d' % num_objects)

    return bpy.context.scene.objects[0]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Generates a blend with 2 keyframes and a moving camera.')
    parser.add_argument(
        '--stl_file', action='store', type=str, required=True)
    parser.add_argument(
        '--output_blend', action='store', type=str, required=True)
    parser.add_argument(
        '--for_symmetry_detection', action='store_true', default=False)
    parser.add_argument(
        '--add_blend_suffix', action='store_true', default=False)

    # Parse only arguments after --
    # --------------------------------------------------------------------------
    argv = sys.argv
    if "--" not in argv:
        argv = []  # as if no args are passed
    else:
        argv = argv[argv.index("--") + 1:]
    args = parser.parse_args(argv)

    # Import
    geo_util.delete_all_objects()
    obj = import_stl(args.stl_file)
    geo_util.fix_normals([obj])

    # Scale object to 1x1x1 box and center at origin
    bbox = geo_util.get_obj_bbox(obj)
    max_dim = max(bbox.get_dims())
    for i in range(3):
        obj.scale[i] = 1.0 / max_dim
        obj.location[i] = 0.0

    # In this mode we set up a downward facing camera and keyframe it to rotate
    # in order to detect rotational symmetry around Z axis through rendering
    suffix = ''
    render_util.set_width_height(750, 750)
    if args.for_symmetry_detection:
        # Number of symmetric parts translates to rotation angle; only
        # prime # parts needs to be checked, as e.g. 6-part symmetry will also
        # fire for 3 and 2 part check.
        nparts = [ 1, 2, 3, 5, 7, 9, 11, 13, 17 ]

        bpy.ops.object.camera_add(location=Vector((0, 0, 3.0)))
        cam = bpy.context.object
        cam.data.clip_start = 0.01
        cam.data.clip_end = 1000
        cam.rotation_euler[0] = 0.0
        cam.rotation_euler[1] = 0.0

        bpy.context.scene.frame_start = 0
        bpy.context.scene.frame_end = len(nparts) - 1

        for i in range(len(nparts)):
            bpy.context.scene.frame_current = i
            cam.rotation_euler[2] = 2 * math.pi / nparts[i]
            cam.keyframe_insert(data_path="rotation_euler", index=2, frame=i)
    else:
        # Rotate an object in a random way
        obj.rotation_mode = 'AXIS_ANGLE'
        obj.rotation_axis_angle[0] = random.random() * 2.0 * math.pi
        axis = geo_util.random_axis()
        for i in range(3):
            obj.rotation_axis_angle[i + 1] = axis[i]

        # Add camera
        bpy.ops.object.camera_add(location=Vector((4.0, 0.0, 0.0)))
        cam = bpy.context.object
        cam.data.clip_start = 0.001
        cam.data.clip_end = 100.0

        camera_loc = cam.matrix_world.to_translation()
        direction = -camera_loc
        rot_quat = direction.to_track_quat('-Z', 'Y')
        cam.rotation_euler = rot_quat.to_euler()

        # Create keyframes
        bpy.context.scene.frame_start = 0
        bpy.context.scene.frame_end = 1

        # Move object randomly
        bpy.context.scene.frame_current = 0
        x = max(-4.0, min(2.0, np.random.normal()))
        ymax = x * -0.375 + 1.5
        print('X %0.3f, ymax %0.3f' % (x, ymax))
        obj.location[0] = x
        obj.location[1] = random.random() * ymax * 2.0 - ymax
        obj.location[2] = random.random() * ymax * 2.0 - ymax

        obj.keyframe_insert(data_path="location", frame=0)

        # Add translation
        # 0 -- simple translation in yz plane
        # 1 -- translation in x,y,z
        suffix = '_simple'
        bpy.context.scene.frame_current = 1
        if random.randrange(0, 2) == 1:
            suffix = '_scale'
            print('Adding 3-axis translation')
            x = max(-4.0, min(2.0, np.random.normal()))
            ymax = x * -0.375 + 1.5
        obj.location[0] = x
        obj.location[1] = random.random() * ymax * 2.0 - ymax
        obj.location[2] = random.random() * ymax * 2.0 - ymax
        obj.keyframe_insert(data_path="location", frame=1)

        # Add random object rotation in its own local frame
        if random.randrange(0, 2) == 1:
            # Note: empty is necessary to allow local frame rotation
            bpy.ops.object.empty_add(type='PLAIN_AXES')
            empty = bpy.context.scene.objects.active
            empty.hide_render = True
            empty.rotation_mode = 'AXIS_ANGLE'
            obj.parent = empty

            bpy.context.scene.frame_current = 0
            empty.keyframe_insert(data_path="rotation_axis_angle", frame=0)

            bpy.context.scene.frame_current = 1
            empty.rotation_axis_angle[0] = (random.random() * 2.0 - 1.0) * math.pi * 0.2
            print('Keyframing object rotation at angle %0.3f' % empty.rotation_axis_angle[0])
            suffix = suffix + '_rot'  # .%0.2f' % empty.rotation_axis_angle[0]
            axis = geo_util.random_axis()
            for i in range(3):
                empty.rotation_axis_angle[i + 1] = axis[i]
            empty.keyframe_insert(data_path="rotation_axis_angle", frame=1)

    outname = args.output_blend
    if args.add_blend_suffix:
        outname = re.sub(r'\.blend', suffix + '.blend', outname)

    geo_util.save_blend(outname)
    print('Saved %s' % outname)
