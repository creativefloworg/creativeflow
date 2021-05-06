"""
Utilities related to rendering, mostly containing blender-specific code that relies on Blender 2.79 built-in API
(bpy, bpy_extras and mathutils packages).
"""
import bpy
import random
import os
import sys
import re
import glob
import logging

LOG = logging.getLogger(__name__)

# IMPORTS ----------------------------------------------------------------------

# Add to path to make sure we can import modules
__sdir = os.path.dirname(os.path.realpath(__file__))  # only works if starts from cmdline
if len(__sdir) <= 1:
    try:
        # Only works if script opened manually inside blender
        __sdir = os.path.dirname(bpy.context.space_data.text.filepath)
    except Exception as e:
        print('Could not get path of current script: %s' % str(e))

if __sdir not in sys.path:
    sys.path.append(__sdir)

# Import stuff that relies on path
import io_util
from misc_util import generate_unique_colors
from motion_util import group_mixamo_vertex_groups
import geo_util

# UTILS ------------------------------------------------------------------------

__NORMALS_NODE_NAME = "StymoNormalsOutput"


def print_blend_diagnostics():
    if len(bpy.data.scenes) != 1 or len(bpy.context.scene.render.layers) != 1:
        print('Warning: this blend has multiple scenes and render layers ' +
              'that are not explicitly handled by our scripts')


def clear_unnecessary_settings():
    """ Clears any unnecessary settings for rendering or objects, such as
    textures, etc.

    Input:
    style - enum of type RenderStyle
    TBD - may need to take in scene/set of objects.
    """
    scene = bpy.context.scene
    rl = scene.render.layers.active
    rl.use_halo = False
    rl.use_zmask = False
    rl.use_all_z = False
    rl.use_ztransp = False
    rl.invert_zmask = False
    rl.use_sky = False
    rl.use_edge_enhance = False
    rl.use_strand = False


def set_world():
    """ Resets world properties. """
    new_world = bpy.data.worlds.new("cartoonFlowWorld")
    bpy.context.scene.world = new_world
    bpy.context.scene.world.horizon_color = (1, 1, 1)


def set_render_settings(use_cycles, nsamples=None, enable_gamma=False):
    """ Sets default render settings appropriate for the rendering engine. """
    scene = bpy.context.scene

    if enable_gamma:
        scene.view_settings.view_transform = 'Default'
    else:
        scene.display_settings.display_device = 'sRGB'
        scene.view_settings.view_transform = 'Raw'

    if use_cycles:
        scene.render.engine = 'CYCLES'
        scene.cycles.film_transparent = True
        if nsamples:
            scene.cycles.samples = nsamples
    else:
        scene.render.engine = 'BLENDER_RENDER'
        scene.render.alpha_mode = 'TRANSPARENT'

    # Defaults for image output
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.image_settings.color_depth = '8'


def disable_all_render_layers():
    for layer in bpy.context.scene.render.layers:
        print('Disabling render layer: %s' % layer.name)
        layer.use = False


def _get_matching_indexes(matching_regexp, names_list, check_found=False):
    matching_idxs = []
    allow_none = "none" in matching_regexp
    for i in range(len(names_list)):
        if re.search(matching_regexp, names_list[i]) and (allow_none or "none" not in names_list[i]):
            matching_idxs.append(i)
    if check_found and len(matching_idxs) == 0:
        raise RuntimeError(
            'Nothing matched "%s" in %s' %
            (matching_regexp, ','.join(names_list)))
    return matching_idxs


def set_linestyle(lines_blend, matching_regexp, color=None,
                  separate_layer=False):
    """
    Sets linestyle by choosing from existing styles in a blend.
    E.g. styles.blend.
    """
    if not os.path.isfile(lines_blend):
        raise RuntimeError('Error: cannot open blend "%s"' % lines_blend)

    with bpy.data.libraries.load(lines_blend) as (data_from, data_to):
        data_to.linestyles = data_from.linestyles
        data_to.textures = data_from.textures

    matching_idxs = _get_matching_indexes(
        matching_regexp, [x.name for x in data_to.linestyles], check_found=True)
    idx = matching_idxs[random.randint(0, len(matching_idxs) - 1)]
    linestyle_name = data_to.linestyles[idx].name
    print(','.join([x.name for x in data_to.linestyles]))
    print('Selecting linestyle %s out of %d' % (linestyle_name, len(matching_idxs)))

    scene = bpy.context.scene
    if separate_layer:
        # Note: this actually does not fully work to isolate line rendering
        disable_all_render_layers()
        lname = 'StyMo_Lines%d' % random.randint(0, 10000)
        line_layer = scene.render.layers.new(lname)
        line_layer.use = True
        scene.render.layers.active = bpy.context.scene.render.layers[lname]
        # We disable rendering of any actual content
        for i in range(len(scene.render.layers[lname].layers_exclude)):
            scene.render.layers[lname].layers_exclude[i] = True
    else:
        line_layer = scene.render.layers.active

    # Disable other linesets
    for k in line_layer.freestyle_settings.linesets.keys():
        line_layer.freestyle_settings.linesets[k].show_render = False

    scene.render.use_freestyle = True
    line_layer.freestyle_settings.linesets.new("stymo")
    line_layer.freestyle_settings.linesets["stymo"].linestyle = data_to.linestyles[idx]
    line_layer.freestyle_settings.linesets["stymo"].show_render = True

    if color:
        for i in range(3):
            line_layer.freestyle_settings.linesets["stymo"].linestyle.color[i] = color[i]

    return linestyle_name


def set_materials(materials_blend, matching_regexp, color_randomizer=None,
                  special_vertex_group_pattern='STYMO:',
                  global_special_vertex_group_suffix='Character'):
    """
    Sets materials by choosing from existing styles in a blend.
    E.g. styles.blend. Vertex group parameters help assign different materials
    to different vertex groups manually marked for our MIXAMO characters.
    """
    if not os.path.isfile(materials_blend):
        raise RuntimeError('Error: cannot open blend "%s"' % materials_blend)

    with bpy.data.libraries.load(materials_blend) as (data_from, data_to):
        data_to.materials = data_from.materials
        data_to.textures = data_from.textures

    matching_idxs = _get_matching_indexes(
        matching_regexp, [x.name for x in data_to.materials], check_found=True)
    idx = matching_idxs[random.randint(0, len(matching_idxs) - 1)]
    mat_name = data_to.materials[idx].name

    def create_mat(name):
        if color_randomizer and 'nocolor' not in data_to.materials[idx].name:
            print('Randomizing material color')
            mat = data_to.materials[idx].copy()
            color = color_randomizer()
            for i in range(3):
                mat.diffuse_color[i] = color[i]
            return mat
        else:
            return data_to.materials[idx]

    set_object_vertexgroup_materials(
        create_mat,
        bg_mat=None,  # We want equally random materials for background as well
        bg_name=None,
        special_vertex_group_pattern=special_vertex_group_pattern,
        global_special_vertex_group_suffix=global_special_vertex_group_suffix)

    return mat_name


def render_animation(output_prefix, max_frames, start_frame_offset=0,
                     render_exr=False, skip_existing=False):
    """
    Main rendering function for rendering metadata or frames from blender.
    Ensures consistent naming and consistent settings.
    """
    scene = bpy.context.scene
    if render_exr:
        # TODO: figure out how to handle multiple render layers
        scene.render.use_motion_blur = False
        scene.render.layers[0].use_pass_vector = True
        scene.render.layers[0].use_pass_z = True
        scene.render.layers[0].use_pass_normal = True
        scene.render.image_settings.file_format = 'OPEN_EXR_MULTILAYER'
        scene.render.image_settings.color_depth = '32'

    else:
        scene.render.image_settings.file_format = 'PNG'
        scene.render.image_settings.color_depth = '8'

    start_frame = scene.frame_start + start_frame_offset
    end_frame = scene.frame_end

    if max_frames >= 0:
        end_frame = min(scene.frame_end, start_frame + max_frames - 1)

    for i in range(start_frame, end_frame + 1):
        relative_fnum = i - start_frame + start_frame_offset + 1  # 1-based
        scene.frame_set(i)

        # Note: we use relative_fnum, which requires setting all paths manually.
        # It seems there is no way to prevent blender from appending a frame
        # number to the output of a FileOutputNode, so we include both and then
        # rename the files.
        tree = bpy.context.scene.node_tree
        if tree and tree.nodes and __NORMALS_NODE_NAME in tree.nodes:
            tree.nodes[__NORMALS_NODE_NAME].file_slots[0].path = 'normal%06d_######' % relative_fnum
        scene.render.filepath = "%s%06d" % (output_prefix, relative_fnum)

        if skip_existing:
            existing = glob.glob("%s.*" % scene.render.filepath)
            if len(existing) > 0:
                LOG.info('Skipping frame %d, exists: %s' %
                         (i, ','.join(existing)))
                continue

        bpy.ops.render.render(animation=False, write_still=True)


def set_width_height(width, height):
    """
    Sets width and height of the output image.

    Input:
    width - int, width of the output image
    height - int, height of the output image
    """
    scene = bpy.context.scene
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100


def find_special_vertex_groups(special_vertex_group_pattern,
                               bg_name=None):
    """
    While ordinary vertex groups may have little semantic information, we
    accept annotated models with special vertex groups, prefixed with a keyword.
    This function finds all such vertex group names across all visible objects
    that are not marked as background (using bg_name keyword).
    """
    scene = bpy.context.scene
    special_vertex_groups = set()
    for ob in scene.objects:
        if ob.type in ['MESH'] and not ob.hide_render and \
                ((bg_name is None) or (bg_name not in ob.name)):
            if len(ob.vertex_groups) > 0:
                special_vertex_groups.update(
                    [g for g in ob.vertex_groups.keys() if
                     re.match(special_vertex_group_pattern, g)])
    return special_vertex_groups


def get_global_vertex_group_bbox(vg_name):
    """
    Computes bound box of a named vertex group that may span more than one
    object.
    """
    scene = bpy.context.scene
    bbox = None

    for ob in scene.objects:
        if ob.type in ['MESH'] and not ob.hide_render:
            if vg_name in ob.vertex_groups:
                vg_idx = ob.vertex_groups[vg_name].index
                vs = [v for v in ob.data.vertices if vg_idx in [vg.group for vg in v.groups]]
                for v in vs:
                    coord = [v.co.x, v.co.y, v.co.z]
                    if bbox:
                        bbox.expand_to_contain(coord)
                    else:
                        bbox = geo_util.BBox(coord, coord)
    return bbox


def sort_special_vertex_groups(vgroups,
                               special_vertex_group_pattern='STYMO:',
                               global_special_vertex_group_suffix='Character'):
    """
    Given a list of special vertex group names, all with the prefix of
    special_vertex_group_pattern, selects all that start with global_special_vertex_group_suffix
    and puts them at the start of the list. This enables e.g. to easily define
    top-level vertex groups that always go first, followed by details that
    overwrite top level assignments.
    """
    global_vg_name_pattern = special_vertex_group_pattern + \
                             global_special_vertex_group_suffix
    first = []
    last = []
    for g in vgroups:
        if re.match(global_vg_name_pattern, g) is not None:
            first.append(g)
        else:
            last.append(g)

    first.sort()
    last.sort()
    first.extend(last)
    return first


def get_objects_and_special_vertex_groups(bg_name,
                                          special_vertex_group_pattern):
    """
    Count number of unique objects (or special "global" vertex groups)
    Note: mixamo data can sometimes split e.g. face into several meshes
    or group all objects into one mesh. If the blend is annotated with
    special global vertex groups, these vertex groups will be labeled
    with the same material even if the vertices belong to different objects.
    """
    scene = bpy.context.scene
    reg_objects = []
    bg_objects = []
    special_vertex_groups = list(find_special_vertex_groups(
        special_vertex_group_pattern, bg_name))

    for ob in scene.objects:
        if ob.type in ['MESH'] and not ob.hide_render:
            if (bg_name is not None) and (bg_name in ob.name):
                bg_objects.append(ob.name)
            else:
                reg_objects.append(ob.name)

    return bg_objects, reg_objects, special_vertex_groups


def set_object_vertexgroup_materials(create_mat_func,
                                     bg_mat,
                                     bg_name,
                                     special_vertex_group_pattern,
                                     global_special_vertex_group_suffix):
    scene = bpy.context.scene
    bg_objects, reg_objects, special_vertex_groups = get_objects_and_special_vertex_groups(
        bg_name, special_vertex_group_pattern)
    print('Found %d bg objects, %d regular objects, %d special vertex groups' %
          (len(bg_objects), len(reg_objects), len(special_vertex_groups)))

    # Create special, global materials
    global_mats = {gname: create_mat_func(gname) for gname in sorted(special_vertex_groups)}

    # Assign materials to objects, creating non-global object materials
    geo_util.ensure_object_mode()
    bpy.ops.object.select_all(action='DESELECT')

    obj_names = bg_objects + reg_objects
    obj_names.sort()
    for ob_name in obj_names:
        print('Processing object %s' % ob_name)
        ob = scene.objects[ob_name]
        geo_util.ensure_object_mode()
        ob.data.materials.clear()

        if ob.name in bg_objects:
            ob.data.materials.append(bg_mat)
        else:
            bpy.context.scene.objects.active = ob
            ob.select = True

            # Create object material
            mat = create_mat_func(ob.name)
            ob.data.materials.append(mat)
            ob.active_material = mat

            try:
                geo_util.ensure_blender_mode('EDIT')
                bpy.ops.mesh.select_all(action='SELECT')
                ob.active_material_index = len(ob.data.materials) - 1
                bpy.ops.object.material_slot_assign()

                # Sort vertex groups so that global vertex groups are processed first,
                # ensuring that detailed vertex groups override high level groups
                gnames = sort_special_vertex_groups(
                    [g for g in ob.vertex_groups.keys() if g in global_mats],
                    special_vertex_group_pattern=special_vertex_group_pattern,
                    global_special_vertex_group_suffix=global_special_vertex_group_suffix)

                for gname in gnames:
                    geo_util.ensure_blender_mode('EDIT')

                    # Find global material
                    mat = global_mats[gname]
                    ob.data.materials.append(mat)

                    # Select the vertex group
                    bpy.ops.mesh.select_all(action='DESELECT')
                    bpy.ops.object.vertex_group_set_active(group=gname)
                    bpy.ops.object.vertex_group_select()

                    # Assign material to vertex group
                    ob.active_material_index = len(ob.data.materials) - 1
                    bpy.ops.object.material_slot_assign()
                    # print('Assigning material %s' % mat.name)

                    bpy.ops.mesh.select_all(action='DESELECT')

            except Exception as exc:
                print('Failed to assign material to vertices; unknown cause.')
                print(exc)

            ob.select = False

    geo_util.ensure_object_mode()


def set_objectids_style(bg_name=None,
                        special_vertex_group_pattern='STYMO:',
                        global_special_vertex_group_suffix='Character',
                        deterministic=False):
    """
    Sets rendering style for rendering object ids.
    The logic here ensures that we also use special vertex groups as a proxy for objects
    in order to appropriately label mixamo characters.
    """
    res = []
    scene = bpy.context.scene
    scene.render.use_compositing = False
    scene.render.use_sequencer = False
    scene.render.use_sss = False
    scene.render.use_world_space_shading = False
    scene.render.use_textures = False
    scene.render.use_shadows = False
    scene.render.use_envmaps = False
    scene.render.use_raytrace = False
    scene.render.use_antialiasing = False
    scene.render.use_freestyle = False
    scene.render.use_motion_blur = False

    bg_objects, reg_objects, special_vertex_groups = get_objects_and_special_vertex_groups(
        bg_name=bg_name, special_vertex_group_pattern=special_vertex_group_pattern)
    nids = len(reg_objects) + len(special_vertex_groups)

    # Create unique colors
    colors = generate_unique_colors(nids)
    if not deterministic:
        random.shuffle(colors)


    def create_mat_from_color(color, name):
        mat = bpy.data.materials.new(name=('Mat_' + name))
        mat.use_shadeless = True
        mat.use_mist = False
        mat.diffuse_color = [float(color[i]) / 255.0 for i in range(3)]
        return mat


    def create_mat(name):
        color = colors[len(res)]
        res.append((name, color))
        return create_mat_from_color(color, name)


    bg_mat = create_mat_from_color([0.0, 0.0, 0.0], 'BG')

    set_object_vertexgroup_materials(
        create_mat,
        bg_mat=bg_mat,
        bg_name=bg_name,
        special_vertex_group_pattern=special_vertex_group_pattern,
        global_special_vertex_group_suffix=global_special_vertex_group_suffix)

    return res


def set_correspondence_style(bg_name=None,
                             special_vertex_group_pattern='STYMO:',
                             global_special_vertex_group_suffix='Character'):
    """
    Sets rendering style for rendering correspondences.
    The logic here ensures that we also use special vertex groups as a proxy for objects
    in order to appropriately render mixamo characters.
    """
    scene = bpy.context.scene
    scene.render.use_textures = False
    scene.render.use_shadows = False
    scene.render.use_envmaps = False
    scene.render.use_raytrace = False
    scene.render.use_freestyle = False
    scene.render.use_motion_blur = False

    # Create shadeless material
    mat = bpy.data.materials.new(name='AbCv_VertexMat')
    mat.use_shadeless = True
    mat.use_vertex_color_paint = True
    mat.use_mist = False

    bg_objects, reg_objects, special_vertex_groups = get_objects_and_special_vertex_groups(
        bg_name=bg_name, special_vertex_group_pattern=special_vertex_group_pattern)

    special_vertex_groups = sort_special_vertex_groups(
        special_vertex_groups,
        special_vertex_group_pattern=special_vertex_group_pattern,
        global_special_vertex_group_suffix=global_special_vertex_group_suffix)

    # Get joint bounding box for all background objects, because background
    # objects all share the same objectid and vertex color must be unique across
    # all of these objects.
    bg_bb = None
    for oname in bg_objects:
        obb = geo_util.get_obj_bbox(scene.objects[oname], obj_space=True)
        if bg_bb is None:
            bg_bb = obb
        else:
            bg_bb.merge_with(obb)

    # Assign unique position-based vertex color to every object
    geo_util.ensure_object_mode()
    bpy.ops.object.select_all(action='DESELECT')
    for ob in scene.objects:
        if ob.name in reg_objects or ob.name in bg_objects:
            print('Prociessing %s' % ob.name)
            bpy.ops.object.select_all(action='DESELECT')
            ob.data.materials.clear()

            bpy.context.scene.objects.active = ob
            ob.select = True
            ob.data.materials.append(mat)
            ob.active_material = mat

            try:
                geo_util.ensure_blender_mode('EDIT')
                bpy.ops.mesh.select_all(action='SELECT')
                ob.active_material_index = len(ob.data.materials) - 1
                bpy.ops.object.material_slot_assign()
                geo_util.ensure_object_mode()
            except Exception as e:
                print('Failed to assign material to vertices; unknown cause.')
                print(e)

            if ob.name in reg_objects:
                bb = geo_util.get_obj_bbox(ob, obj_space=True)
            else:
                bb = bg_bb
            assign_vertex_colors(ob, bb)

    # Assign unique position-based vertex colors to groups as well, using
    # bounding box for the group
    for vg_name in special_vertex_groups:
        vg_bb = get_global_vertex_group_bbox(vg_name)

        for ob_name in reg_objects:
            assign_vertex_colors(scene.objects[ob_name], vg_bb, vg_name)


def assign_vertex_colors(obj, bbox, vertex_group_name=None):
    """
    Assigns vertex colors to all vertices in the object using each vertex's xyz
    position in the provided bbox. If bbox is computed for the obg, this has
    the effect of assigning a unique color to every vertex with maximum possible
    dynamic range. If vertex_group_name is provided, only sets colors for vertices
    in that vertex group.
    """
    geo_util.ensure_object_mode()

    vg_idx = -1
    if vertex_group_name:
        if vertex_group_name not in obj.vertex_groups:
            return
        else:
            vg_idx = obj.vertex_groups[vertex_group_name].index

    denoms = [x[0] - x[1] for x in zip(bbox.maxs, bbox.mins)]
    for j in range(3):
        if denoms[j] < 1e-5:
            denoms[j] = 1.0

    def to_color(coords):
        res = [0, 0, 0]
        for j in range(3):
            res[j] = max(0.0, min(1.0, (coords[j] - bbox.mins[j]) / denoms[j]))
        return res

    mesh = obj.data

    if 'corr' not in mesh.vertex_colors.keys():
        # Remove existing vertex colors
        for vcolorkey in mesh.vertex_colors.keys():
            mesh.vertex_colors.remove(mesh.vertex_colors[vcolorkey])
        mesh.vertex_colors.new('corr')

    color_layer = mesh.vertex_colors['corr']
    mesh.vertex_colors.active = color_layer

    i = 0
    for poly in mesh.polygons:
        for idx in poly.loop_indices:
            vidx = mesh.loops[idx].vertex_index
            v = mesh.vertices[vidx]
            # If specified, limit to a specific vertex group
            if (not vertex_group_name) or (vg_idx in [vg.group for vg in v.groups]):
                co = to_color(v.co)
                color_layer.data[i].color = [co[0], co[1], co[2]]
            i += 1


def assign_unique_object_ids(bg_name=None):
    scene = bpy.context.scene
    idx = 1
    res = []
    for ob in scene.objects:
        if ob.type not in ['CAMERA', 'LAMP', 'ARMATURE']:
            if (bg_name is not None) and (bg_name in ob.name):
                ob.pass_index = 0  # Background gets a special ID=0
            else:
                ob.pass_index = idx
                res.append((idx, ob.name))
                idx += 1
    return res


def count_vertex_groups(bg_name=None):
    scene = bpy.context.scene
    count = 0
    for ob in scene.objects:
        if ob.type in ['MESH']:
            if (bg_name is None) or (bg_name not in ob.name):
                if not ob.hide_render:
                    count += 1
                    count += len(group_mixamo_vertex_groups(ob.vertex_groups.keys()))
    return count


def init_render_nodes():
    bpy.context.scene.use_nodes = True
    bpy.context.scene.render.layers[0].use_pass_combined = True
    bpy.context.scene.render.use_compositing = True

    tree = bpy.context.scene.node_tree

    # Clear the default nodes
    for n in tree.nodes:
        tree.nodes.remove(n)

    rl = tree.nodes.new('CompositorNodeRLayers')
    rl.location = 0, 200
    return rl


def init_normals_render_nodes(normals_output_dir, use_cycles=False):
    rl = init_render_nodes()
    enable_render_normals(rl, normals_output_dir, use_cycles=use_cycles)


def enable_render_normals(rl, output_folder, use_cycles):
    bpy.context.scene.render.layers[0].use_pass_normal = True

    tree = bpy.context.scene.node_tree

    multiply = tree.nodes.new('CompositorNodeMixRGB')
    multiply.blend_type = 'MULTIPLY'
    multiply.inputs[2].default_value = (.5, .5, .5, 1)
    multiply.location = 200, 200

    add = tree.nodes.new('CompositorNodeMixRGB')
    add.blend_type = 'ADD'
    add.inputs[2].default_value = (.5, .5, .5, 1)
    add.location = 400, 200

    output = tree.nodes.new('CompositorNodeOutputFile')
    output.name = __NORMALS_NODE_NAME
    output.base_path = output_folder
    output.format.file_format = 'PNG'
    output.format.color_depth = '16'
    output.format.color_mode = 'RGBA'
    output.file_slots[0].path = 'normal######'
    output.location = 800, 200

    links = tree.links
    links.new(rl.outputs['Normal'], multiply.inputs[1])
    links.new(multiply.outputs[0], add.inputs[1])

    # Note: BLENDER and CYCLES normals are completely different.
    if use_cycles:
        links.new(add.outputs[0], output.inputs[0])
    else:
        invert = tree.nodes.new('CompositorNodeInvert')
        invert.invert_rgb = True
        links.new(add.outputs[0], invert.inputs[1])
        links.new(invert.outputs[0], output.inputs[0])
    return add


def setup_realistic_lighting(envmap_path, hdrLightStrength, useAsBackground):
    """
    Sets up realistic lighting using an hdr image.

    :param envmap_path: (String)the path to the hdr image
    :param hdrLightStrength: (float/int)the intensity of the light emitted from the hdr
         image data the default strength value in blender is 1
    :param useAsBackground: (True/False)Embed the hdr image in the render background
    """
    if os.path.isdir(envmap_path):
        paths = io_util.get_images_in_dir(envmap_path)
        if len(paths) == 0:
            raise RuntimeError('Error: no environment maps found in %s' % envmap_path)
        hdrPath = os.path.join(envmap_path, paths[random.randint(0, len(paths) - 1)])
    elif os.path.isfile(envmap_path):
        hdrPath = envmap_path
    else:
        raise RuntimeError('Error: invalid environment map path %s' % envmap_path)

    bpy.context.scene.render.engine = 'BLENDER_RENDER'

    if len(bpy.data.worlds) == 0:
        bpy.ops.world.new()

    bpy.context.scene.world = bpy.data.worlds[0]
    bpy.context.scene.world.use_sky_real = True
    bpy.context.scene.world.light_settings.use_environment_light = True
    bpy.context.scene.world.light_settings.environment_color = 'SKY_TEXTURE'
    bpy.context.scene.world.light_settings.environment_energy = hdrLightStrength

    BackGroundTex = bpy.data.textures.new('BackGroundColor', type='IMAGE')
    BackGroundTex.image = bpy.data.images.load(hdrPath)

    if bpy.data.worlds[0].texture_slots[0] is None:
        mTex = bpy.data.worlds[0].texture_slots.add()
    else:
        mTex = bpy.data.worlds[0].texture_slots[0]

    mTex.texture = BackGroundTex
    mTex.texture_coords = 'EQUIRECT'
    mTex.use_map_blend = False
    mTex.use_map_horizon = True

    if useAsBackground:
        bpy.context.scene.render.alpha_mode = 'SKY'
    else:
        bpy.context.scene.render.alpha_mode = 'TRANSPARENT'
