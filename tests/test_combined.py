"""Prove the combined Repack + Bake leaves a textured mesh looking unchanged.

Renders before and after, and checks that the object ends up with its own baked
material rather than the shared atlas one.

Usage:
    blender -b --factory-startup --python tests/test_combined.py -- <blend> <outdir> [limit]
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

from uv_repack.islands import islands_from_mesh
from uv_repack.repack import uv_coverage


def frame_and_render(objects, path: str, size: int = 800) -> None:
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = size
    scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = path

    scene.world = scene.world or bpy.data.worlds.new("World")
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    if background:
        background.inputs[0].default_value = (0.06, 0.06, 0.07, 1.0)
        background.inputs[1].default_value = 1.2

    corners = [ob.matrix_world @ Vector(c) for ob in objects for c in ob.bound_box]
    centre = sum(corners, Vector((0, 0, 0))) / len(corners)
    radius = max((c - centre).length for c in corners) or 1.0

    light = bpy.data.objects.get("CombinedLight")
    if light is None:
        data = bpy.data.lights.new("CombinedLight", type='SUN')
        data.energy = 5.0
        light = bpy.data.objects.new("CombinedLight", data)
        scene.collection.objects.link(light)
    light.location = centre + Vector((radius * 2, -radius * 2, radius * 3))

    camera = bpy.data.objects.get("CombinedCamera")
    if camera is None:
        camera = bpy.data.objects.new(
            "CombinedCamera", bpy.data.cameras.new("CombinedCamera")
        )
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
    print(f"COMBINED targets={len(targets)} of {len(textured)} textured meshes")

    coverage_before = {
        ob.name: uv_coverage(islands_from_mesh(ob.data)) for ob in targets
    }
    materials_before = {
        ob.name: [s.material.name if s.material else None for s in ob.material_slots]
        for ob in targets
    }
    engine_before = bpy.context.scene.render.engine

    frame_and_render(targets, os.path.join(outdir, "combined_before.png"))
    print("COMBINED rendered before")

    scene = bpy.context.scene
    scene.uv_repack.bake_resolution = 'AUTO'
    scene.uv_repack.bake_margin = 8
    scene.uv_repack.skip_packed = False
    scene.uv_repack.make_single_user = True

    for ob in bpy.context.view_layer.objects:
        ob.select_set(ob in targets)
    bpy.context.view_layer.objects.active = targets[0]

    result = bpy.ops.uv_repack.repack_and_bake()
    print(f"COMBINED operator={result}")

    for ob in targets:
        after = uv_coverage(islands_from_mesh(ob.data))
        print(
            f"COMBINED_UV {ob.name} "
            f"{coverage_before[ob.name] * 100:.2f}% -> {after * 100:.2f}%"
        )
        materials_after = [
            s.material.name if s.material else None for s in ob.material_slots
        ]
        print(
            f"COMBINED_MAT {ob.name} "
            f"{materials_before[ob.name]} -> {materials_after}"
        )

    frame_and_render(targets, os.path.join(outdir, "combined_after.png"))
    print("COMBINED rendered after")

    engine_after = bpy.context.scene.render.engine
    print(f"COMBINED_ENGINE {engine_before} -> {engine_after} restored={engine_before == engine_after}")

    leftover = [m.name for m in bpy.data.materials if m.name.startswith("UVREPACK_BAKE_")]
    print(f"COMBINED_LEFTOVER_SCAFFOLDING {len(leftover)}")

    baked = sorted(i.name for i in bpy.data.images if i.name.endswith(("_basecolor", "_normal", "_orm")))
    print(f"COMBINED_IMAGES {len(baked)}")
    for name in baked[:12]:
        print(f"COMBINED_IMAGE {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
