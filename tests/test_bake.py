"""Prove the bake pipeline on a real textured scene.

Loads the given .blend, bakes the selected objects at a small resolution, and
reports whether the baked images actually contain the original texture's detail
rather than a flat fill. Writes nothing back to the source file.

Usage:
    blender -b --factory-startup --python tests/test_bake.py -- <blend> [resolution] [object_limit]
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
from uv_repack.repack import uv_coverage
from uv_repack.nodes import recommended_resolution


def image_stats(image) -> dict:
    """Spread of pixel values, to tell real detail from a flat fill."""
    buffer = [0.0] * (image.size[0] * image.size[1] * 4)
    image.pixels.foreach_get(buffer)
    rgb = [buffer[i] for i in range(len(buffer)) if i % 4 != 3]
    if not rgb:
        return {"min": 0.0, "max": 0.0, "mean": 0.0, "unique": 0}
    return {
        "min": min(rgb),
        "max": max(rgb),
        "mean": sum(rgb) / len(rgb),
        "unique": len({round(v, 3) for v in rgb}),
    }


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not argv:
        print("BAKE_TEST no blend file given")
        return 2
    blend = argv[0]
    resolution = int(argv[1]) if len(argv) > 1 else 256
    limit = int(argv[2]) if len(argv) > 2 else 1

    bpy.ops.wm.open_mainfile(filepath=blend)
    addon_utils.enable("uv_repack", default_set=True)

    atlas = None
    for image in bpy.data.images:
        if image.source == 'FILE' and image.size[0] > 0:
            atlas = image
            break
    if atlas is not None:
        stats = image_stats(atlas)
        print(
            f"  ATLAS {atlas.name} {atlas.size[0]}px cs={atlas.colorspace_settings.name} "
            f"mean={stats['mean']:.3f} unique={stats['unique']}"
        )

    targets = [
        ob for ob in bpy.context.view_layer.objects
        if ob.type == 'MESH' and ob.data.polygons and ob.data.uv_layers.active
    ][:limit]
    if not targets:
        print("BAKE_TEST no textured meshes found")
        return 2

    print(f"BAKE_TEST targets={len(targets)} resolution={resolution}")

    before_coverage = [uv_coverage(islands_from_mesh(ob.data)) for ob in targets]
    before_materials = [
        [slot.material.name if slot.material else None for slot in ob.material_slots]
        for ob in targets
    ]
    atlas_resolution = atlas.size[0] if atlas is not None else 2048
    for ob, coverage in zip(targets, before_coverage):
        print(
            f"  SOURCE {ob.name} coverage={coverage * 100:.2f}% "
            f"recommended={recommended_resolution(coverage, atlas_resolution)}px "
            f"polys={len(ob.data.polygons)}"
        )

    repack(targets, margin=0.001, skip_policy=None)
    after_coverage = [uv_coverage(islands_from_mesh(ob.data)) for ob in targets]
    print("  REPACK " + " ".join(
        f"{ob.name}:{b * 100:.1f}%->{a * 100:.1f}%"
        for ob, b, a in zip(targets, before_coverage, after_coverage)
    ))

    report = bake_objects(targets, resolution, margin=8)
    print("  BAKE", report.summary())
    for failure in report.failures:
        print(f"  BAKE_FAIL {failure.name}: {failure.error}")

    for result in report.baked:
        for key, image_name in sorted(result.images.items()):
            image = bpy.data.images.get(image_name)
            if image is None:
                print(f"  MISSING {image_name}")
                continue
            stats = image_stats(image)
            print(
                f"  IMAGE {result.name}/{key} {image.size[0]}px "
                f"cs={image.colorspace_settings.name} "
                f"min={stats['min']:.3f} max={stats['max']:.3f} "
                f"mean={stats['mean']:.3f} unique={stats['unique']}"
            )

    after_materials = [
        [slot.material.name if slot.material else None for slot in ob.material_slots]
        for ob in targets
    ]
    print(f"  MATERIALS_UNCHANGED {before_materials == after_materials}")

    # Does the bake actually reproduce the atlas, rather than merely being
    # non-empty? Compare mean colour of the original to the baked base colour.
    for result in report.baked:
        baked = bpy.data.images.get(result.images.get("basecolor", ""))
        if baked is None or atlas is None:
            continue
        source_stats = image_stats(atlas)
        baked_stats = image_stats(baked)
        delta = abs(source_stats["mean"] - baked_stats["mean"])
        print(
            f"  FIDELITY atlas_mean={source_stats['mean']:.3f} "
            f"baked_mean={baked_stats['mean']:.3f} delta={delta:.3f} "
            f"plausible={delta < 0.2}"
        )
        normal = bpy.data.images.get(result.images.get("normal", ""))
        if normal is not None:
            normal_stats = image_stats(normal)
            print(
                f"  NORMAL_RANGE min={normal_stats['min']:.3f} "
                f"max={normal_stats['max']:.3f} mean={normal_stats['mean']:.3f}"
            )
    return 0 if report.baked and not report.failures else 1


if __name__ == "__main__":
    sys.exit(main())
