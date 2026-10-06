"""Does the baked base colour match the atlas at the same UV points?

Repacking changes UV coordinates, so this compares the atlas sampled at the
ORIGINAL uvs against the bake sampled at the NEW uvs, per polygon.

Usage:
    blender -b --factory-startup --python tests/verify_bake_matches.py -- <blend>
"""

import os
import sys

import bpy
import numpy

ADDON_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ADDON_PARENT not in sys.path:
    sys.path.insert(0, ADDON_PARENT)

import addon_utils

addon_utils.enable("uv_repack", default_set=True)

from uv_repack.api import repack
from uv_repack.bake import bake_object


def centroid_uvs(mesh):
    data = mesh.uv_layers.active.data
    out = []
    for polygon in mesh.polygons:
        loops = list(polygon.loop_indices)
        u = sum(data[i].uv.x for i in loops) / len(loops)
        v = sum(data[i].uv.y for i in loops) / len(loops)
        out.append((u, v))
    return out


def sample(image, points):
    width, height = image.size
    buffer = numpy.empty(len(image.pixels), dtype=numpy.float32)
    image.pixels.foreach_get(buffer)
    pixels = buffer.reshape(height, width, 4)
    out = []
    for u, v in points:
        x = min(max(int(u * width), 0), width - 1)
        y = min(max(int(v * height), 0), height - 1)
        out.append(pixels[y, x, :3])
    return numpy.array(out)


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    bpy.ops.wm.open_mainfile(filepath=argv[0])
    addon_utils.enable("uv_repack", default_set=True)

    target = next(
        ob for ob in bpy.context.view_layer.objects
        if ob.type == 'MESH' and ob.data.uv_layers.active
        and any(s.material and any(
            n.type == 'TEX_IMAGE' and n.image for n in s.material.node_tree.nodes
        ) for s in ob.material_slots if s.material)
    )
    atlas = next(
        i for i in bpy.data.images if i.source == 'FILE' and i.size[0] > 0
    )
    old_points = centroid_uvs(target.data)
    print(f"VERIFY obj={target.name} atlas={atlas.name} polys={len(old_points)}")

    for ob in bpy.context.view_layer.objects:
        ob.select_set(ob is target)
    bpy.context.view_layer.objects.active = target
    repack([target], margin=0.001, skip_policy=None)

    new_points = centroid_uvs(target.data)
    result = bake_object(target, 512, 8)
    if not result.ok:
        print(f"VERIFY bake failed: {result.error}")
        return 1

    baked = bpy.data.images.get(result.slots[0].images["basecolor"])
    source_values = sample(atlas, old_points)
    baked_values = sample(baked, new_points)

    delta = numpy.abs(source_values - baked_values).mean(axis=1)
    print(
        f"VERIFY samples={len(delta)} mean_delta={delta.mean():.4f} "
        f"median={numpy.median(delta):.4f} p90={numpy.percentile(delta, 90):.4f} "
        f"within_2pct={(delta < 0.02).mean() * 100:.1f}%"
    )
    worst = numpy.argsort(delta)[-3:]
    for index in worst:
        print(
            f"VERIFY worst poly={index} old={old_points[index]} new={new_points[index]} "
            f"atlas={source_values[index].round(3)} baked={baked_values[index].round(3)}"
        )
    for index in range(3):
        print(
            f"VERIFY sample poly={index} old={tuple(round(c, 3) for c in old_points[index])} "
            f"new={tuple(round(c, 3) for c in new_points[index])} "
            f"atlas={source_values[index].round(3)} baked={baked_values[index].round(3)}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
