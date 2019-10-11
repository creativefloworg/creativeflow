"""
Utilities specific to rendering assets needed to stylize the frames using
Stylit algorithm (Fiser et al, SIGGRAPH 2016). Uses blender 2.79 built-in API.
"""
import bpy
import mathutils
import random

import geo_util


def create_stylit_material():
    """ Creates red shiny material for rendering input to Stylit. """
    mat = bpy.data.materials.new(name="stylit_mat")
    mat.use_nodes = True
    tree = mat.node_tree

    for n in tree.nodes:
        tree.nodes.remove(n)

    diffuse = tree.nodes.new('ShaderNodeBsdfDiffuse')
    diffuse.inputs[0].default_value = (1, 0, 0, 1)
    diffuse.inputs[1].default_value = 0.25

    glossy = tree.nodes.new('ShaderNodeBsdfGlossy')
    glossy.inputs[0].default_value = (1, 0.05, 0.05, 1)
    glossy.inputs[1].default_value = 0.1

    mix = tree.nodes.new('ShaderNodeMixShader')
    output = tree.nodes.new('ShaderNodeOutputMaterial')

    links = tree.links
    links.new(diffuse.outputs[0], mix.inputs[1])
    links.new(glossy.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], output.inputs[0])
    return mat


def create_light(bbox, cam, dist, lamp_data):
    """ Creates light for lighting objects consistently in order to render input for stylit. """
    cam_obj = cam.data

    # create light for each camera
    # light position is relative to the input camera
    center = bbox.get_center()
    radius = (cam.location - mathutils.Vector((center[0], center[1], center[2]))).length

    # Always rotate to the right, to match stylit render
    angle = -random.uniform(cam_obj.angle * 0.5, cam_obj.angle)
    mat_rot = mathutils.Matrix.Rotation(angle, 4, 'Y')

    disp = cam.matrix_world.to_quaternion() * mat_rot.to_quaternion() * \
           mathutils.Vector((0.0, 0.0, -random.uniform(0.5, 0.75) * radius))
    light_pos = cam.location + disp

    lamp_object = bpy.data.objects.new(name="New Lamp", object_data=lamp_data)
    bpy.context.scene.objects.link(lamp_object)
    lamp_object.location = light_pos
    lamp_object.select = True
    bpy.context.scene.objects.active = lamp_object
    set_light_params(lamp_data, radius)


def set_light_params(lamp, modifier):
    # bpy.data.lamps['Lamp'].cycles.max_bounces = 0
    lamp.cycles.max_bounces = 0
    lamp.shadow_soft_size = 0.3 * modifier
    lamp.use_nodes = True
    lamp.node_tree.nodes['Emission'].inputs['Strength'].default_value = 800 * modifier


def setup_stylit_lighting():
    """ Sets up lighting for the blend in order to render input for Stylit. """
    geo_util.delete_all_objects_of_type('LAMP')

    cam = geo_util.get_single_camera_or_die()
    info = None
    for obj in bpy.data.objects:
        if obj.data is not None and obj.type not in ['CAMERA', 'LAMP', 'ARMATURE']:
            bbox = geo_util.get_obj_bbox(obj)
            dist = geo_util.distance_from_camera_center(bbox, cam)
            if info is None or dist < info[1]:
                info = (bbox, dist)  # Find closest object to view center

    if info is not None:
        lamp_data = bpy.data.lamps.new(name="New Lamp", type='POINT')
        create_light(info[0], cam, info[1], lamp_data)


def setup_stylit_materials(bg_name=None):
    """ Sets up materials (for background and foreground separately) on order to render Stylit input."""
    mat = create_stylit_material()

    for obj in bpy.data.objects:
        if obj.data is not None and obj.type not in ['CAMERA', 'LAMP', 'ARMATURE']:
            obj.data.materials.clear()  # BG gets none material
            if (bg_name is None) or (bg_name not in obj.name):
                obj.data.materials.append(mat)
                obj.active_material = mat
