"""
MAIN STYLING AND RENDERING FILE

Requirements:
------------------------------------------------------------------------------
IMPORTANT! This has only been tested with Blender 2.79 API. We have run this
on Linux and MacOS.

Execution:
------------------------------------------------------------------------------
This script is intended to run inside blender launched in background mode.
Sample invocation is:
blender --background --factory-startup --python-exit-code 1 PATH_TO_MY_BLEND.blend \
         --python blender/render_main.py -- \
         --width=500 <ANY OTHER PYTHON FLAGS FROM render_main.py>

'--factory-startup' is used to prevent custom settings from interfering.
'--python-exit-code 1' makes blender exit with code 1 if this script throws an error
'--' causes blender to ignore all following arguments so python can use them.

See blender --help for details. See pipeline.sh for sample usage.

Capabilities:
------------------------------------------------------------------------------
It is assumed that blender is invoked with a single blend. This script is a
jack-of-all-trades for setting up camera, lighting, styling, and rendering for
a custom stylized animation benchmark. We found it easier to run the script
separately for each phase of data processing (see pipeline.sh),
as this way the output can be easily examined for problems after every stage.
However, one-shot execution should also be possible.

See flags below for full capabilities. The trickiest bit is: different metadata
only works with particular render engine option. The script will raise errors
if incorrect engine is specified:
 - Vertex paint for correspondences - blender render (no gamma correction!)
 - Normals in camera space - blender render (no gamma correction!)
 - Flow vector pass - cycles (blender render is buggy)
 - Red stylit reference material - cycles
 - Env lighting for mixamo models - blender render only
"""
import bpy

import argparse
import logging
import os
import random
import sys
import time
import traceback


# Add to path to make sure we can import modules while running inside Blender.
__sdir = os.path.dirname(os.path.realpath(__file__))
if __sdir not in sys.path:
    sys.path.append(__sdir)

import color_util
import geo_util
import io_util
import render_util
import stylit_util

LOG = logging.getLogger(__name__)


if __name__ == "__main__":
    try:
        # FLAGS
        # --------------------------------------------------------------------------
        parser = argparse.ArgumentParser(
            description='Configurable utility to modify blend and/or render images/flow/metadata.')

        parser.add_argument(
            '--random_seed', action='store', type=int, default=-1,
            help='Integer seed for random number generator; used if > 0.')

        # Rendering ----------------------------------------------------------------
        parser.add_argument(
            '--width', action='store', type=int, default=1500,
            help='Width to render at.')
        parser.add_argument(
            '--height', action='store', type=int, default=1500,
            help='Height to render at.')
        parser.add_argument(
            '--quality_samples', action='store', type=int, default=-1,
            help='If positive and using cycles, will use this many samples per pixel; ' +
            'e.g. 128 is slow, 10 is comparatively fast.')

        parser.add_argument(
            '--start_frame', action='store', type=int, default=0,
            help='Frame to start rendering at (relative to first frame).')
        parser.add_argument(
            '--rendered_frames', action='store', type=int, default=0,
            help='Maximum frames to render; 0 for none; -1 for all.')
        parser.add_argument(
            '--skip_existing_frames', action='store_true', default=False,
            help='If true, skips existing frames matching --frame_output_prefix.')

        parser.add_argument(
            '--use_cycles', action='store_true', default=False,
            help='If true, sets Cycles as the rendering engine, else leaves unchanged.')
        parser.add_argument(
            '--use_blender_render', action='store_true', default=False,
            help='If true, sets Blender Render as the rendering engine, else leaves unchanged.')

        # Outputs ------------------------------------------------------------------
        parser.add_argument(
            '--frame_output_prefix', action='store', type=str, default='',
            help='If set, will set image output to <frame_output_prefix><frame#>.PNG; ' +
            'should include full path.')
        parser.add_argument(
            '--render_metadata_exr', action='store_true', default=False,
            help='If true, renders all metadata passes as a multilayer EXR file.')
        parser.add_argument(
            '--objectids_key_file', action='store', type=str, default='',
            help='Directory to write objectids to, as images.')
        parser.add_argument(
            '--world_normals_output_dir', action='store', type=str, default='',
            help='Directory to write world space normals to, as images ' +
            '(only compatible with --use_cycles.')
        parser.add_argument(
            '--camera_normals_output_dir', action='store', type=str, default='',
            help='Directory to write camera space normals to, as images ' +
            '(only compatible with --use_blender_render.')
        parser.add_argument(
            '--enable_gamma_correction', action='store_true', default=False,
            help='We disable gamma correction by default, as it corrupts the ' +
            'metadata rendering; set this on to enable.')
        parser.add_argument(
            '--bg_name', action='store', type=str, default="STYMO_BG",
            help='If any object name matches this substring, it will be treated as ' +
            'background for the purpose of id labeling and stylit rendering.')

        parser.add_argument(
            '--output_blend', action='store', type=str, default='',
            help='If set, will output modified blend here (must be absolute path); ' +
            'if setting linestyle and/or material, will replace special substrings ' +
            '<M> and <L> with material and linestyle.')
        parser.add_argument(
            '--info_file', action='store', type=str, default='',
            help='If set, may output auxiliary information into this file.')

        # Camera -------------------------------------------------------------------
        parser.add_argument(
            '--set_camera', action='store', type=int, default=0,
            help='If >= 0, selects ith camera and deletes all other cameras; ' +
            'if i > num cameras, generates a random one instead.')
        parser.add_argument(
            '--keep_extra_cameras', action='store_true',
            help='If --set_camera, will not delete extra cameras.')
        parser.add_argument(
            '--add_random_camera_motion', action='store_true',
            help='If generating a random camera and this is true, creates zoom/flyaround/pan; '
                 'WARNING: parameters are tuned for mixamo character blends.')

        # Animation range ----------------------------------------------------------
        parser.add_argument(
            '--offset_scene_start_frame_by', action='store', type=int, default=0,
            help='Unlike --start_frame, which just controls the rendering range, this ' +
            'flag offsets the current scene start frame in the timeline by the ' +
            'specified amount. Relevant to blends that do not begin at frame 0.')
        parser.add_argument(
            '--offset_scene_end_frame_by', action='store', type=int, default=0,
            help='Unlike --rendered_frames, which just controls the rendering range, this ' +
            'flag offsets the current scene end frame in the timeline by the ' +
            'specified amount. Relevant to blends that do not begin at frame 0.')

        # Lighting -----------------------------------------------------------------
        parser.add_argument(
            '--set_env_lighting_image', action='store', type=str, default='',
            help='Set to image path or directory of environment map images to set ' +
            'environment lighting; only works with --use_blender_render.')
        parser.add_argument(
            '--set_stylit_lighting', action='store_true',
            help='If true, sets consistent lighting to render input for stylit.')

        # Styles -------------------------------------------------------------------
        parser.add_argument(
            '--set_stylit_style', action='store_true',
            help='If true, sets red material style used for stylit style transfer.')

        parser.add_argument(
            '--set_corresp_style', action='store_true',
            help='If true, will set per-vertex materials to render correspondences.')
        parser.add_argument(
            '--set_objectids_style', action='store_true',
            help='If true, will set objectids to render using flat materials.')
        parser.add_argument(
            '--deterministic_objectid_colors', action='store_true',
            help='If true, objectid colors will not be shuffled; use for testing.')

        parser.add_argument(
            '--linestyles_blend', action='store', type=str, default='',
            help='Path to blend containing all the line styles.')
        parser.add_argument(
            '--set_linestyle_matching', action='store', type=str, default='',
            help='Regex matching linestyle(s) in --line_styles_blend; '
            'if more than one match, picks random one; ' 
            '"" for none; ".*" for all; "hi|bye" to match either.')
        parser.add_argument(
            '--randomize_line_color', action='store_true',
            help='If true, randomizes line color if line is set.')

        parser.add_argument(
            '--materials_blend', action='store', type=str, default='',
            help='Path to blend containing all the material styles (e.g. textured blender styles).')
        parser.add_argument(
            '--set_materials_matching', action='store', type=str, default='',
            help='Regex matching materials(s) in --materials_blend; ' 
            'if more than one match, picks random one; ' 
            '"" for none; ".*" for all; "hi|bye" to match either.')
        parser.add_argument(
            '--randomize_material_color', action='store_true',
            help='If true, randomizes material color if material is set.')

        # Custom color control
        parser.add_argument(
            '--material_color_choices', action='store', type=str, default='',
            help='String of format R,G,B R2,G2,B2 ... of colors to choose from if ' +
            'randomizing material colors.')
        parser.add_argument(
            '--line_hue_range', action='store', type=str, default='0,1.0',
            help='If --randomize_line_color, will keep HSV Hue in this range (two numbers,csv).')
        parser.add_argument(
            '--line_sat_range', action='store', type=str, default='0,1.0',
            help='If --randomize_line_color, will keep HSV Saturation in this range (two numbers,csv).')
        parser.add_argument(
            '--line_value_range', action='store', type=str, default='0,1.0',
            help='If --randomize_line_color, will keep HSV Value in this range (two numbers,csv).')

        # Parse only arguments after --
        # --------------------------------------------------------------------------
        argv = sys.argv
        if "--" not in argv:
            argv = []  # as if no args are passed
        else:
            argv = argv[argv.index("--") + 1:]
        args = parser.parse_args(argv)

        if args.random_seed > 0:
            print('Using --random_seed=%d as random seed.' % args.random_seed)
            random.seed(args.random_seed)
        else:
            print('Using time as random seed.')
            random.seed(time.time())

        render_util.print_blend_diagnostics()

        # Handle camera ------------------------------------------------------------
        if args.set_camera >= 0:
            cam = None
            if args.keep_extra_cameras:
                cam = geo_util.get_camera_by_number(args.set_camera)
            else:
                cam = geo_util.delete_all_but_one_camera(args.set_camera)

            if cam is None:
                print('Generating a random camera.')
                bbox = geo_util.get_scene_bbox()
                cam = geo_util.create_random_camera(bbox, 2.5, 2.5, 2.5)

            if args.add_random_camera_motion:
                print('Adding motion to camera.')
                geo_util.mixamo_add_random_camera_motion(cam)

            geo_util.disable_camera_depth_of_field(cam)
        else:
            cam = geo_util.get_single_camera_or_die()

        # Set active camera
        bpy.context.scene.camera = cam

        # Handle frame bounds ------------------------------------------------------

        orig_start = bpy.context.scene.frame_start
        bpy.context.scene.frame_start = orig_start + args.offset_scene_start_frame_by
        if args.offset_scene_end_frame_by > 0:
            bpy.context.scene.frame_end = orig_start + args.offset_scene_end_frame_by

        # Handle lighting ----------------------------------------------------------
        info_file = None
        if args.info_file:
            info_file = open(args.info_file, 'w')

        if len(args.set_env_lighting_image) > 0:
            if not args.use_blender_render:
                raise RuntimeError(
                    'Error: --set_env_lighting_image="img" only works with --use_blender_render')
            render_util.setup_realistic_lighting(args.set_env_lighting_image, 10.0, False)

        if args.set_stylit_lighting:
            if not args.use_cycles:
                raise RuntimeError(
                    'Error: --set_stylit_lighting only works with --use_cycles')
            stylit_util.setup_stylit_lighting()

        # Handle styles ------------------------------------------------------------
        nstyles = len([x for x in [args.set_stylit_lighting,
                                   args.set_corresp_style, args.set_objectids_style,
                                   (args.set_linestyle_matching or args.set_materials_matching)]
                       if x])
        if nstyles > 1:
            raise RuntimeError(
                'Error: incompatible rendering styles specified; only one of these can be true: ' +
                '--set_stylit_lighting OR ' +
                '--set_corresp_style OR --set_objectids_style OR ' +
                '(--set_linestyle_matching and/or --set_materials_matching)')

        linestyle_name = 'default'
        material_name = 'default'
        if args.set_stylit_style:  # Red material used for stylit rendering
            if not args.use_cycles:
                raise RuntimeError(
                    'Error: --set_stylit_style only works with --use_cycles')
            render_util.clear_unnecessary_settings()
            stylit_util.setup_stylit_materials(bg_name=args.bg_name)
        elif args.set_corresp_style:  # Per-vertex correspondence rendering
            if not args.use_blender_render:
                raise RuntimeError(
                    'Correspondence rendering (--set_corresp_style) only implemented for ' +
                    '--use_blender_render')
            render_util.clear_unnecessary_settings()
            render_util.set_correspondence_style()
        elif args.set_objectids_style:  # Object Ids rendered in flat color
            if not args.use_blender_render:
                raise RuntimeError(
                    'Correspondence rendering (--set_objectids_style) only implemented for ' +
                    '--use_blender_render')
            render_util.clear_unnecessary_settings()
            idsinfo = render_util.set_objectids_style(
                bg_name=args.bg_name, deterministic=args.deterministic_objectid_colors)

            if idsinfo and args.objectids_key_file:
                with open(os.path.join(args.objectids_key_file), 'w') as f:
                    for i in range(len(idsinfo)):
                        f.write('%s %d %d %d\n' %
                                (idsinfo[i][0], idsinfo[i][1][0],
                                 idsinfo[i][1][1], idsinfo[i][1][2]))
        elif args.set_linestyle_matching or args.set_materials_matching:  # Freestyle / toon shading
            if not args.use_blender_render:
                raise RuntimeError(
                    'Linestyles and materials only implemented for --use_blender_render')
            render_util.clear_unnecessary_settings()

            if len(args.set_linestyle_matching) > 0:
                if len(args.linestyles_blend) == 0:
                    raise RuntimeError(
                        'Error: Must set --linestyles_blend with line exemplars ' +
                        'if requesting --set_linestyle_matching.')

                line_color = None
                if args.randomize_line_color:
                    line_color = color_util.get_random_color(
                        prob_dark=0.8,
                        bounds=color_util.parse_hsv_bounds(args.line_hue_range,
                                                           args.line_sat_range,
                                                           args.line_value_range))

                linestyle_name = render_util.set_linestyle(
                    args.linestyles_blend, args.set_linestyle_matching,
                    color=line_color)

                if info_file:
                    info_file.write('LINESTYLE %s\n' % io_util.strip_blender_name(linestyle_name))

            if len(args.set_materials_matching) > 0:
                if len(args.materials_blend) == 0:
                    raise RuntimeError(
                        'Error: Must set --materials_blend with material ' +
                        'exemplars if requesting --set_materials_matching.')

                mat_color_randomizer = None
                if args.randomize_material_color:
                    if args.material_color_choices:
                        mat_color_randomizer = color_util.make_color_getter(
                            args.material_color_choices)
                    else:
                        mat_color_randomizer = color_util.make_random_color_getter()

                material_name = render_util.set_materials(
                    args.materials_blend, args.set_materials_matching,
                    color_randomizer=mat_color_randomizer)

                if info_file:
                    info_file.write('MATSTYLE %s\n' % io_util.strip_blender_name(material_name))

        # Handle rendering settings ------------------------------------------------
        if args.use_cycles and args.use_blender_render:
            raise RuntimeError('Can specify only one of --use_cycles and --use_blender_render')

        if args.use_cycles or args.use_blender_render:
            nsamples = (args.quality_samples if args.quality_samples > 0 else None)
            render_util.set_render_settings(args.use_cycles, nsamples=nsamples,
                                            enable_gamma=args.enable_gamma_correction)

        if args.width > 0 and args.height > 0:
            render_util.set_width_height(args.width, args.height)

        if args.world_normals_output_dir or args.camera_normals_output_dir:
            if args.world_normals_output_dir and args.camera_normals_output_dir:
                raise RuntimeError('Only one type of normals can be output at once.')
            if args.world_normals_output_dir and not args.use_cycles:
                raise RuntimeError('World normals can only be output with --use_cycles.')
            elif args.camera_normals_output_dir and not args.use_blender_render:
                raise RuntimeError('Camera space normals can only be output with --use_blender_render.')

            render_util.init_normals_render_nodes(
                (args.world_normals_output_dir or args.camera_normals_output_dir),
                use_cycles=args.use_cycles)

        # Handle saving -------------------------------------------------------
        if len(args.output_blend) > 0:
            bpy.ops.file.pack_all()
            args.output_blend = args.output_blend.replace('<M>', io_util.strip_blender_name(material_name))
            args.output_blend = args.output_blend.replace('<L>', io_util.strip_blender_name(linestyle_name))
            print('Saving blend to %s' % args.output_blend)
            geo_util.save_blend(args.output_blend)

        if args.rendered_frames != 0:
            if args.render_metadata_exr and not args.use_cycles:
                raise RuntimeError('Must set --use_cycles=True to render out flow with ' +
                                   '--render_metadata_exr')

            print('Rendering frames')
            render_util.render_animation(
                args.frame_output_prefix, args.rendered_frames,
                start_frame_offset=args.start_frame,
                render_exr=args.render_metadata_exr,
                skip_existing=args.skip_existing_frames)

    except Exception as e:
        tb = traceback.format_exc()
        LOG.critical(tb)
        LOG.critical('Script failed')
        raise e

    LOG.critical('Script completed')
