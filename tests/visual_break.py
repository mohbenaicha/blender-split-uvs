"""Render a textured mesh before and after repacking, to show the texture break.

Usage:
    blender -b --factory-startup --python tests/visual_break.py -- <blend> <outdir>
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

from uv_repack.api import repack


def frame_and_render(objects, path: str, size: int = 800) -> None:
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = size
    scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = False
    scene.render.filepath = path
    scene.world = scene.world or bpy.data.worlds.new("World")
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    if background:
        background.inputs[0].default_value = (0.05, 0.05, 0.06, 1.0)
        background.inputs[1].default_value = 1.0

    corners = [ob.matrix_world @ Vector(c) for ob in objects for c in ob.bound_box]
    centre = sum(corners, Vector((0, 0, 0))) / len(corners)
    radius = max((c - centre).length for c in corners) or 1.0

    light = bpy.data.objects.get("BreakLight")
    if light is None:
        data = bpy.data.lights.new("BreakLight", type='SUN')
        data.energy = 5.0
        light = bpy.data.objects.new("BreakLight", data)
        scene.collection.objects.link(light)
    light.location = centre + Vector((radius * 2, -radius * 2, radius * 3))

    camera = bpy.data.objects.get("BreakCamera")
    if camera is None:
        camera = bpy.data.objects.new("BreakCamera", bpy.data.cameras.new("BreakCamera"))
        scene.collection.objects.link(camera)
    camera.data.lens = 50
    camera.location = centre + Vector((radius * 1.3, -radius * 2.6, radius * 0.9))
    camera.rotation_euler = (centre - camera.location).to_track_quat('-Z', 'Y').to_euler()
    scene.camera = camera

    bpy.ops.render.render(write_still=True)


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    blend, outdir = argv[0], argv[1]
    limit = int(argv[2]) if len(argv) > 2 else 6

    bpy.ops.wm.open_mainfile(filepath=blend)
    addon_utils.enable("uv_repack", default_set=True)

    textured = [
        ob for ob in bpy.context.view_layer.objects
        if ob.type == 'MESH' and ob.data.uv_layers.active
        and any(s.material and any(
            n.type == 'TEX_IMAGE' and n.image for n in s.material.node_tree.nodes
        ) for s in ob.material_slots if s.material)
    ]
    targets = textured[:limit]
    print(f"BREAK targets={len(targets)} of {len(textured)} textured meshes")

    frame_and_render(targets, os.path.join(outdir, "before_repack.png"))
    print("BREAK rendered before")

    repack(targets, margin=0.001, skip_policy=None)
    print("BREAK repacked")

    frame_and_render(targets, os.path.join(outdir, "after_repack.png"))
    print("BREAK rendered after")
    return 0


if __name__ == "__main__":
    sys.exit(main())
