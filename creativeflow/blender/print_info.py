import argparse
import bpy
import os
import re
import sys

# Add to path to make sure we can import modules
__sdir = os.path.dirname(os.path.realpath(__file__))
if __sdir not in sys.path:
    sys.path.append(__sdir)

import geo_util


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--import_file', action='store', type=str, default='')

    argv = sys.argv
    if "--" not in argv:
        argv = []  # as if no args are passed
    else:
        argv = argv[argv.index("--") + 1:]
    args = parser.parse_args(argv)

    if len(args.import_file) > 0:
        geo_util.delete_all_objects()

        if re.match('.*.dae', args.import_file):
            bpy.ops.wm.collada_import(filepath=args.import_file)
        elif re.match('.*.fbx', args.import_file):
            bpy.ops.import_scene.fbx(filepath=args.import_file)
        else:
            raise RuntimeError(
                '--import_file set to unsupported format, only .dae and .fbx ' +
                ('supported: %s' % args.import_file))

    start_frame = bpy.context.scene.frame_start
    end_frame = bpy.context.scene.frame_end

    # print("INFO_INFO: %d %d %d" % ( start_frame, end_frame, end_frame-start_frame+1))
    # print('INFO_INFO: %d %d' % (len(bpy.data.scenes), len(bpy.context.scene.render.layers)))
    # keyframes = motion_util.get_keyframe_range(bpy.data.objects['Armature'])
    # print('INFO_INFO: %d %d' % (keyframes[0], keyframes[1]))
    print('INFO_INFO: %s' % str(bpy.context.scene.render.use_motion_blur))
    # names = bpy.data.objects['Armature'].pose.bones.keys()
    # names = bpy.data.objects.keys()
    # names.sort()
    # print('INFO_INFO: %s' % ' '.join(names))

    # names = bpy.data.objects['Armature'].pose.bones.keys()
    # names = bpy.data.objects.keys()
    # names.sort()
    # print('INFO_INFO2: %s' % ' '.join(names))
