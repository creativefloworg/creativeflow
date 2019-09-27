"""
ANIMATE RIGID OBJECTS IN BLENDER.

Requirements:
------------------------------------------------------------------------------
IMPORTANT! This has only been tested with Blender 2.79 API.

Warnings:
------------------------------------------------------------------------------
Do not expect all blends to be perfect; we did additional filtering of
generated blends to ensure that random data is well-formed.

Execution:
------------------------------------------------------------------------------
This script is intended to run inside blender launched in background mode.
Sample invocation is:

blender --background --python-exit-code 1 --factory-startup \
            --python blender/animate_main.py -- \
            --set_env_lighting_image=$ENVMAPS \
            --obj_file="$OBJ" \
            --output_blend="$OFILE"

Capabilities:
------------------------------------------------------------------------------
Uses Blender's rigid body simulator to animate objects in the input file and
output a blend file with the animation.
"""
import bpy

import argparse
import logging
import math
import os
import sys
import random
import time
import traceback


# Add to path to make sure we can import modules inside Blender.
__sdir = os.path.dirname(os.path.realpath(__file__))
if __sdir not in sys.path:
    sys.path.append(__sdir)

import rigid_body_util
import geo_util
import render_util

LOG = logging.getLogger(__name__)


if __name__ == "__main__":
    try:
        # FLAGS
        # --------------------------------------------------------------------------
        parser = argparse.ArgumentParser(
            description='Utility to animate shapenet models randomly.')
        parser.add_argument(
            '--obj_file', action='store', type=str, required=True,
            help='Input OBJ file.')
        parser.add_argument(
            '--simple_diagnostic', action='store_true', default=False,
            help='If true, does not animate, but just imports and runs diagnostic info.')
        parser.add_argument(
            '--set_env_lighting_image', action='store', default='',
            help='Image or directory of images; set to set environment lighting.')
        parser.add_argument(
            '--p_breaking', action='store', type=float, default=0.5,
            help='Probability of breaking.')
        parser.add_argument(
            '--p_cam_track', action='store', type=float, default=0.5)
        parser.add_argument(
            '--p_bouncy', action='store', type=float, default=0.3)
        parser.add_argument(
            '--p_warp_time', action='store', type=float, default=0.3)
        parser.add_argument(
            '--p_tilt_floor', action='store', type=float, default=0.2)
        parser.add_argument(
            '--diagnostic_frame_prefix', action='store', default='')
        parser.add_argument(
            '--output_blend', action='store', type=str, required=True)

        # Parse only arguments after --
        # --------------------------------------------------------------------------
        argv = sys.argv
        if "--" not in argv:
            argv = []  # as if no args are passed
        else:
            argv = argv[argv.index("--") + 1:]
        args = parser.parse_args(argv)

        random.seed(time.time())
        render_util.set_width_height(1500, 1500)

        if args.set_env_lighting_image:
            render_util.setup_realistic_lighting(args.set_env_lighting_image, 3.0, False)

        if args.simple_diagnostic:
            rigid_body_util.obj_import_diagnostic(args.obj_file)

            cam = geo_util.create_random_camera(
                geo_util.BBox([-1.0,-1.0,0.0], [1.0, 1.0, 1.0]),
                1.0, 1.0, 1.0)
        else:
            floor, objects = rigid_body_util.obj_import_animate(
                args.obj_file,
                allow_breaking=(random.random() < args.p_breaking))

            cam = geo_util.create_random_camera(
                geo_util.BBox([-1.0,-1.0,0.0], [1.0, 1.0, 1.0]),
                1.0, 1.0, 1.0)

            # Note: one can't truly slow down the simulation without altering
            # the result in blender; empirically this gives a reasonable alternative
            # timing
            if random.random() < args.p_warp_time:
                rigid_body_util.set_rigidbody_world_properties(
                    steps_per_sec=60, time_scale=0.5, solver_its=random.randint(3, 6))

            if random.random() < args.p_tilt_floor:
                axis = random.randint(0, 1)
                angle = random.uniform(-math.pi * 0.2, math.pi * 0.2)
                floor.rotation_euler[axis] = angle

            if random.random() < args.p_bouncy:
                restitution = random.uniform(0.38, 0.5)
                for ob in objects + [floor]:
                    ob.rigid_body.restitution = restitution

            if random.random() < args.p_cam_track:
                geo_util.add_camera_track_constraint(
                    cam, objects[random.randint(0, len(objects) - 1)])

        # bpy.context.scene.world.light_settings.samples = 2
        bpy.ops.file.pack_all()

        print('Saving blend to %s' % args.output_blend.replace('.blend', '_unbaked.blend'))
        geo_util.save_blend(args.output_blend.replace('.blend', '_unbaked.blend'))

        rigid_body_util.bake_simulation_bugfix()
        print('Saving blend to %s' % args.output_blend)
        geo_util.save_blend(args.output_blend)

        if len(args.diagnostic_frame_prefix) > 0:
            render_util.render_animation(args.diagnostic_frame_prefix, 1)

    except Exception as e:
        tb = traceback.format_exc()
        LOG.critical(tb)
        LOG.critical('Script failed')
        raise e
