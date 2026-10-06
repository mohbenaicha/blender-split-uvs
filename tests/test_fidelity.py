"""Pixel-accuracy check: is the baked texture the same colour as the source?

Samples the atlas and the baked base colour at the same UV position and compares
the raw values. A colour-space mistake shows up here as a large delta even
though the images look plausible in isolation.

Usage:
    blender -b --factory-startup --python tests/test_fidelity.py -- <blend> [resolution]
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


def sample_many(image, points):
    """Read the whole buffer once, then look up each point."""
    width, height = image.size
    buffer = [0.0] * (width * height * 4)
    image.pixels.foreach_get(buffer)
    out = []
    for u, v in points:
        x = min(max(int(u * width), 0), width - 1)
        y = min(max(int(v * height), 0), height - 1)
        index = (y * width + x) * 4
        out.append(tuple(buffer[index:index + 3]))
    return out


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    blend = argv[0]
    resolution = int(argv[1]) if len(argv) > 1 else 2048

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

    # Collect the OLD uvs and the polygon centroids before repacking replaces them.
    uv_data = target.data.uv_layers.active.data
    samples = []
    for polygon in list(target.data.polygons)[:400]:
        loops = list(polygon.loop_indices)
        centroid = [0.0, 0.0]
        for loop in loops:
            uv = uv_data[loop].uv
            centroid[0] += uv.x / len(loops)
            centroid[1] += uv.y / len(loops)
        samples.append(tuple(centroid))
    old_points = list(samples)

    repack_enabled = "--norepack" not in argv
    if repack_enabled:
        repack([target], margin=0.0, skip_policy=None)

    # Re-read the same polygon centroids. With --norepack these are identical to
    # the originals, which isolates colour-space handling from UV resampling.
    uv_data = target.data.uv_layers.active.data
    new_points = []
    for polygon in list(target.data.polygons)[:400]:
        loops = list(polygon.loop_indices)
        centroid = [0.0, 0.0]
        for loop in loops:
            uv = uv_data[loop].uv
            centroid[0] += uv.x / len(loops)
            centroid[1] += uv.y / len(loops)
        new_points.append(tuple(centroid))

    report = bake_objects([target], resolution, margin=8)
    baked = bpy.data.images.get(report.baked[0].images["basecolor"])

    normal_name = report.baked[0].images.get("normal")
    normal = bpy.data.images.get(normal_name) if normal_name else None
    normal_source = next(
        (image for image in bpy.data.images
         if image.name not in (atlas.name,) and image.colorspace_settings.name == "Non-Color"
         and image.size[0] > 0 and image.users > 0),
        None,
    )

    atlas_values = sample_many(atlas, old_points)
    baked_values = sample_many(baked, new_points)

    deltas = []
    for (ar, ag, ab), (br, bg, bb) in zip(atlas_values, baked_values):
        deltas.append((abs(ar - br) + abs(ag - bg) + abs(ab - bb)) / 3.0)
    deltas.sort()
    mean = sum(deltas) / len(deltas)
    median = deltas[len(deltas) // 2]
    within = sum(1 for d in deltas if d < 0.02) / len(deltas)

    # An untouched (cleared black) sample means the point missed packed geometry,
    # which is a sampling error rather than a bake error.
    black = sum(1 for value in baked_values if max(value) < 0.01)
    old_in_unit = sum(
        1 for u, v in old_points if 0.0 <= u <= 1.0 and 0.0 <= v <= 1.0
    )
    new_range = (
        min(u for u, _ in new_points), max(u for u, _ in new_points),
        min(v for _, v in new_points), max(v for _, v in new_points),
    )

    print(f"FIDELITY atlas={atlas.name} baked={baked.name} res={resolution} samples={len(deltas)}")
    print(f"FIDELITY mean_delta={mean:.4f} median_delta={median:.4f} within_2pct={within * 100:.1f}%")
    print(f"FIDELITY baked_black_samples={black}/{len(baked_values)} "
          f"old_uv_in_unit={old_in_unit}/{len(old_points)}")
    print(f"FIDELITY new_uv_range u=({new_range[0]:.3f},{new_range[1]:.3f}) "
          f"v=({new_range[2]:.3f},{new_range[3]:.3f})")
    first = (atlas_values[0], baked_values[0])
    print(f"FIDELITY sample0 olduv={tuple(round(c,3) for c in old_points[0])} "
          f"atlas={tuple(round(v, 3) for v in first[0])} "
          f"newuv={tuple(round(c,3) for c in new_points[0])} "
          f"baked={tuple(round(v, 3) for v in first[1])}")

    # A tangent-space normal map is dominated by +Z, so its blue channel must stay
    # high everywhere. A near-zero blue means the normal pass wrote nothing.
    if normal is not None:
        values = sample_many(normal, new_points)
        blues = sorted(value[2] for value in values)
        print(
            f"NORMAL_FIDELITY samples={len(values)} "
            f"blue_min={blues[0]:.3f} blue_median={blues[len(blues) // 2]:.3f} "
            f"blue_max={blues[-1]:.3f} "
            f"any_below_half={sum(1 for b in blues if b < 0.5)}"
        )

        # Compare against the source normal map at the same points. A baked normal
        # that is flatter than its source means the pass dropped the detail.
        linked_normal = None
        for material in target.data.materials:
            if material is None or not material.use_nodes:
                continue
            for node in material.node_tree.nodes:
                if node.type == 'NORMAL_MAP' and node.inputs["Color"].links:
                    upstream = node.inputs["Color"].links[0].from_node
                    if getattr(upstream, "image", None):
                        linked_normal = upstream.image
        if linked_normal is not None:
            source_values = sample_many(linked_normal, old_points)
            source_blues = sorted(value[2] for value in source_values)
            deltas_n = [
                sum(abs(a - b) for a, b in zip(s, d)) / 3.0
                for s, d in zip(source_values, values)
            ]
            deltas_n.sort()
            print(
                f"NORMAL_SOURCE {linked_normal.name} "
                f"blue_min={source_blues[0]:.3f} "
                f"blue_median={source_blues[len(source_blues) // 2]:.3f} "
                f"blue_max={source_blues[-1]:.3f}"
            )
            print(
                f"NORMAL_DELTA mean={sum(deltas_n) / len(deltas_n):.4f} "
                f"median={deltas_n[len(deltas_n) // 2]:.4f}"
            )
    return 0 if median < 0.05 else 1


if __name__ == "__main__":
    sys.exit(main())
