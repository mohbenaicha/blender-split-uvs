"""Render ONE object before and after the combined repack+bake, in isolation.

No other objects, no shared state: if the bake reproduced the atlas, the two
images should be near-identical.

Usage:
    blender -b --factory-startup --python tests/verify_one_object.py -- <blend> <outdir>
"""

import os
import sys

import bpy
from mathutils import Vector

ADDON_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ADDON_PARENT not in sys.path:
    sys.path.insert(0, ADDON_PARENT)

import addon_utils

addon_utils.enable("uv_repack", default_set=True)


def render(path: str, size: int = 512) -> None:
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = size
    scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = path

    scene.world = scene.world or bpy.data.worlds.new("W")
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    if background:
        background.inputs[0].default_value = (0.1, 0.1, 0.12, 1.0)
        background.inputs[1].default_value = 1.5

    target = bpy.context.view_layer.objects.active
    corners = [target.matrix_world @ Vector(c) for c in target.bound_box]
    centre = sum(corners, Vector((0, 0, 0))) / len(corners)
    radius = max((c - centre).length for c in corners) or 1.0

    light = bpy.data.objects.get("OneLight")
    if light is None:
        data = bpy.data.lights.new("OneLight", type='SUN')
        data.energy = 6.0
        light = bpy.data.objects.new("OneLight", data)
        scene.collection.objects.link(light)
    light.location = centre + Vector((radius * 2, -radius * 2, radius * 2.5))

    camera = bpy.data.objects.get("OneCamera")
    if camera is None:
        camera = bpy.data.objects.new("OneCamera", bpy.data.cameras.new("OneCamera"))
        scene.collection.objects.link(camera)
    camera.data.lens = 55
    camera.location = centre + Vector((0.0, -radius * 3.2, radius * 0.6))
    camera.rotation_euler = (centre - camera.location).to_track_quat('-Z', 'Y').to_euler()
    scene.camera = camera
    bpy.ops.render.render(write_still=True)


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    blend, outdir = argv[0], argv[1]
    bpy.ops.wm.open_mainfile(filepath=blend)
    addon_utils.enable("uv_repack", default_set=True)

    target = next(
        ob for ob in bpy.context.view_layer.objects
        if ob.type == 'MESH' and ob.data.uv_layers.active
        and any(s.material and any(
            n.type == 'TEX_IMAGE' and n.image for n in s.material.node_tree.nodes
        ) for s in ob.material_slots if s.material)
    )
    # Hide every other object so only this one is visible.
    for ob in bpy.context.view_layer.objects:
        if ob.type == 'MESH' and ob is not target:
            ob.hide_render = True

    for ob in bpy.context.view_layer.objects:
        ob.select_set(ob is target)
    bpy.context.view_layer.objects.active = target

    render(os.path.join(outdir, "one_before.png"))
    print(f"ONE before rendered, material={target.material_slots[0].material.name}")

    scene = bpy.context.scene
    scene.uv_repack.bake_resolution = '512'
    scene.uv_repack.bake_margin = 8
    scene.uv_repack.skip_packed = False
    result = bpy.ops.uv_repack.repack_and_bake()
    print(f"ONE operator={result}")

    render(os.path.join(outdir, "one_after.png"))
    print(f"ONE after rendered, material={target.material_slots[0].material.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
