"""Render one baked object at three sizes so the difference is visible.

Usage:
    blender -b --factory-startup --python tests/visual_demo.py -- <blend> <outdir>
"""

import os
import sys

import bpy

ADDON_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ADDON_PARENT not in sys.path:
    sys.path.insert(0, ADDON_PARENT)

import addon_utils

addon_utils.enable("uv_repack", default_set=True)

from uv_repack.api import repack
from uv_repack.bake import bake_objects
from uv_repack.islands import islands_from_mesh
from uv_repack.nodes import recommended_resolution
from uv_repack.repack import uv_coverage


def render(objects, path: str, size: int = 700) -> None:
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = size
    scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = path

    camera = bpy.data.objects.get("DemoCamera")
    if camera is None:
        camera = bpy.data.objects.new("DemoCamera", bpy.data.cameras.new("DemoCamera"))
        scene.collection.objects.link(camera)
    camera.data.lens = 60
    scene.camera = camera

    # Frame the objects without relying on an operator that needs a 3D view.
    corners = []
    for ob in objects:
        for corner in ob.bound_box:
            corners.append(ob.matrix_world @ __import__("mathutils").Vector(corner))
    centre = sum(corners, __import__("mathutils").Vector((0, 0, 0))) / len(corners)
    radius = max((c - centre).length for c in corners) or 1.0

    from mathutils import Vector

    for obj_name, location in (
        ("DemoLight", centre + Vector((radius * 2, -radius * 2, radius * 2))),
    ):
        obj = bpy.data.objects.get(obj_name)
        if obj is None:
            data = bpy.data.lights.new(obj_name, type='SUN')
            data.energy = 4.0
            obj = bpy.data.objects.new(obj_name, data)
            scene.collection.objects.link(obj)
        obj.location = location

    camera.location = centre + Vector((radius * 1.6, -radius * 2.4, radius * 1.2))
    direction = centre - camera.location
    camera.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    bpy.ops.render.render(write_still=True)


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    blend, outdir = argv[0], argv[1]

    bpy.ops.wm.open_mainfile(filepath=blend)
    addon_utils.enable("uv_repack", default_set=True)

    target = next(
        ob for ob in bpy.context.view_layer.objects
        if ob.type == 'MESH' and ob.data.uv_layers.active
    )
    atlas = next(
        image for image in bpy.data.images
        if image.source == 'FILE' and image.size[0] > 0
    )

    coverage = uv_coverage(islands_from_mesh(target.data))
    auto = recommended_resolution(coverage, (atlas.size[0], atlas.size[1]))
    print(
        f"DEMO object={target.name} atlas={atlas.size[0]} "
        f"coverage={coverage * 100:.2f}% auto_size={auto}"
    )

    for ob in bpy.context.view_layer.objects:
        ob.select_set(ob is target)
    bpy.context.view_layer.objects.active = target
    repack([target], margin=0.001, skip_policy=None)

    for label, size in (("auto", auto), ("size_256", 256), ("size_2048", 2048)):
        report = bake_objects([target], size, margin=8)
        if report.failures:
            print(f"DEMO_FAIL {label} {report.failures[0].error}")
            continue
        base = bpy.data.images[report.baked[0].images["basecolor"]]
        base.filepath_raw = os.path.join(outdir, f"baked_{label}_{size}.png")
        base.file_format = 'PNG'
        base.save()
        print(f"DEMO_SAVED {label} {size}px -> {base.filepath_raw}")

        # Point the material at this bake so the render shows it.
        for material in target.data.materials:
            if material is None or not material.use_nodes:
                continue
            principled = next(
                (n for n in material.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None
            )
            if principled is None:
                continue
            node = material.node_tree.nodes.get("DEMO_BAKE")
            if node is None:
                node = material.node_tree.nodes.new('ShaderNodeTexImage')
                node.name = "DEMO_BAKE"
            node.image = base
            for link in list(principled.inputs["Base Color"].links):
                material.node_tree.links.remove(link)
            material.node_tree.links.new(
                node.outputs["Color"], principled.inputs["Base Color"]
            )
        render([target], os.path.join(outdir, f"render_{label}_{size}.png"))
        print(f"DEMO_RENDER {label} {size}px")
    return 0


if __name__ == "__main__":
    sys.exit(main())
