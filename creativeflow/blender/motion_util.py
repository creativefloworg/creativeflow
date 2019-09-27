"""
Scripts specific to dealing with motion, in particular motion retargeting of mixamo data. Relies on Blender
2.79 API.
"""
import bpy
import logging
import re

LOG = logging.getLogger(__name__)


def detect_bone_prefix(bones):
    """
    Mixamo data tends to prefix bone names with character names or other prefixes.
    It has been confirmed that in all the mixamo data we collected, such a prefix
    can be determined using this heuristic, achieving a canonical naming if the
    prefix is removed.
    """
    prefix = ''
    for i in range(len(bones)):
        bone = bones[i]
        r = re.match("^(.*)Head$", bone)
        if r is not None:
            prefix = r.group(1)
            print('Detected rig prefix: ' + prefix)
            break
    return prefix


def detect_common_prefix(bones):
    prefix = ''

    if len(bones) == 0:
        return prefix

    max_length = min([len(b) for b in bones])
    for i in range(max_length):
        letter = bones[0][i]

        matched_all = True
        for b in bones:
            if b[i] != letter:
                matched_all = False
                break
        if matched_all:
            prefix = prefix + letter
        else:
            break

    return prefix


def import_retarget_all(target_collada_file, source_fbx_file):
    bpy.ops.wm.collada_import(filepath=target_collada_file)
    import_retarget_motion(source_fbx_file)


def import_retarget_motion(source_fbx_file):
    bpy.ops.import_scene.fbx(filepath=source_fbx_file)
    target_arm = bpy.data.objects['Armature']
    source_arm = bpy.data.objects['Armature.001']
    retarget(target_arm, source_arm)


def retarget(target_arm, source_arm):
    """
    E.g.:
    target_arm = bpy.data.objects['Armature']
    source_arm = bpy.data.objects['Armature.001']
    """

    # Find inconsistent prefixes
    tprefix = detect_bone_prefix(target_arm.pose.bones.keys())
    sprefix = detect_bone_prefix(source_arm.pose.bones.keys())

    # Create source bone dictionary
    src_names = dict([(x.replace(sprefix, ''), x) for x in
                      source_arm.pose.bones.keys()])

    # Set armature bone-bone connections
    for rkey in target_arm.pose.bones.keys():
        # Canonical key
        ckey = rkey.replace(tprefix, '')

        if ckey in src_names:
            target_arm.pose.bones[rkey].name = source_arm.pose.bones[src_names[ckey]].name
        else:
            bpy.ops.object.select_all(action='DESELECT')
            source_arm.select = True
            bpy.ops.object.mode_set(mode='EDIT')
            Newbone = source_arm.data.edit_bones.new(rkey)
            Newbone.head = target_arm.pose.bones[rkey].head / 10
            Newbone.parent = source_arm.data.edit_bones[src_names['Neck']]
            bpy.ops.object.mode_set(mode='OBJECT')
            target_arm.pose.bones[rkey].name = source_arm.pose.bones[rkey].name

    # Set actions
    target_arm.animation_data.action = source_arm.animation_data.action

    # Change modifiers to adjust for a different rest pose
    for i in range(len(target_arm.children)):
        if (target_arm.children[i].type == 'MESH' and
                'Armature' in target_arm.children[i].modifiers):
            target_arm.children[i].modifiers['Armature'].object = source_arm

    # Fix artifacts
    fix_armatures_rotation(target_arm)

    for o in target_arm.children:
        o.modifiers[0].object = target_arm
    hide_source_from_render(source_arm)

    framerange = get_keyframe_range(source_arm)
    scene = bpy.context.scene
    scene.frame_start = framerange[0]
    scene.frame_end = framerange[1]


def hide_source_from_render(source_arm):
    bpy.ops.object.select_all(action='DESELECT')
    source_arm.select = True
    for chi in source_arm.children:
        chi.select = True
        bpy.ops.object.move_to_layer(layers=(False, False, False, False, False, False,
                                             False, False, False, False, False, False,
                                             False, False, False, False, False, False, False, True))
        chi.hide = True
        chi.hide_select = True
        chi.hide_render = True
    source_arm.hide = True
    source_arm.hide_select = True
    source_arm.hide_render = True


def fix_armatures_rotation(target_arm):
    bpy.ops.object.select_all(action='DESELECT')
    target_arm.select = True
    bpy.context.scene.objects.active = target_arm
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.armature.select_all(action='SELECT')
    bpy.ops.armature.roll_clear()
    bpy.ops.object.mode_set(mode='OBJECT')


def get_keyframe_range(obj):
    """
    Returns minimal and maximal frame number of the animation associated with
    the object.
    """
    anim = obj.animation_data
    if not anim or not anim.action:
        return [0, 0]
    res = None
    for fcu in anim.action.fcurves:
        for keyframe in fcu.keyframe_points:
            t = keyframe.co[0]
            if res is None:
                res = [t, t]
            else:
                if t < res[0]:
                    res[0] = t
                if t > res[1]:
                    res[1] = t
    return res


# Note: this does not actually work very well
def group_mixamo_vertex_groups(vertex_group_names):
    prefix = detect_bone_prefix(vertex_group_names)

    group_keys = ["Hips",
                  "Spine",
                  "Head",
                  "Neck"]
    sided_group_keys = [".*Arm",
                        "Shoulder",
                        "Hand",
                        ".*Leg",
                        "((Foot)|(Toe))"]
    covered = set()
    res = []
    for key in group_keys:
        pattern = prefix + key
        matching = [g for g in vertex_group_names if re.match(pattern, g) is not None]
        if len(matching) > 0:
            res.append((key, matching))
            covered.update(matching)

    for key in sided_group_keys:
        for side in ["Left", "Right"]:
            pattern = prefix + side + key
            name = side + key.replace(".", "").replace("*", "").replace("|", "").replace("(", "").replace(")", "")
            matching = [g for g in vertex_group_names if re.match(pattern, g) is not None]
            if len(matching) > 0:
                res.append((name, matching))
                covered.update(matching)

    print('Length of groups is %d' % len(res))
    if len(res) > 0 and len(res) != (len(group_keys) + 2 * len(sided_group_keys)):
        LOG.warning('Not a full mixamo rig discovered for %s' % ','.join(vertex_group_names))
        return []

    if len(covered) != len(vertex_group_names):
        missing = [g for g in vertex_group_names if g not in covered]

        if len(covered) > 0:
            LOG.warning('Some Mixamo vertex groups not covered: %s' % ','.join(missing))

        res.extend([(m, [m]) for m in missing])

    return res
