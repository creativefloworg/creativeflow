"""
RETARGET MOTION TO CHARACTERS.

Background:
------------------------------------------------------------------------------
This script was used to create mixamo animated sequences in Creative Flow.

Requirements:
------------------------------------------------------------------------------
IMPORTANT! This has only been tested with Blender 2.79 API. We have run this
on Linux and MacOS.

Warning:
------------------------------------------------------------------------------
There is absolutely no guarantee this will work for other characters and
motions.

Execution:
------------------------------------------------------------------------------
Sample invocation:

blender --background --python-exit-code 1 --factory-startup \
                    --python blender/retarget_main.py -- \
                    --collada_file="$C" \
                    --fbx_file="$M" \
                    --output_blend="$OFILE"
"""
import argparse
import logging
import sys
import os
import traceback

import bpy

# Add to path to make sure we can import modules inside blender.
__sdir = os.path.dirname(os.path.realpath(__file__))
if __sdir not in sys.path:
    sys.path.append(__sdir)

import motion_util
import geo_util

LOG = logging.getLogger(__name__)


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(
            description='Utility to retarget mixamo fbx files to collada character files.')
        parser.add_argument(
            '--collada_file', action='store', type=str, default='',
            help='Character collada file; if not provided assume character blend is ' +
            'opened instead.')
        parser.add_argument(
            '--fbx_file', action='store', type=str, required=True)
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

        if len(args.collada_file) > 0:
            geo_util.delete_all_objects()
            motion_util.import_retarget_all(args.collada_file, args.fbx_file)
        else:
            motion_util.import_retarget_motion(args.fbx_file)

        bpy.ops.file.pack_all()
        LOG.info('Saving blend to %s' % args.output_blend)
        geo_util.save_blend(args.output_blend)

    except Exception as e:
        tb = traceback.format_exc()
        LOG.critical(tb)
        LOG.critical('Script failed')
        raise e
