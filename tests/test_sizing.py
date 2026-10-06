"""The auto-size rule: smallest square power-of-two texture holding the pixels
the object owned in the original atlas.

Usage:
    blender -b --factory-startup --python tests/test_sizing.py
"""

import os
import sys

import bpy

ADDON_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ADDON_PARENT not in sys.path:
    sys.path.insert(0, ADDON_PARENT)

from uv_repack.nodes import recommended_resolution

# (coverage, atlas size, expected side)
CASES = [
    # 3.59% of 2048^2 = 150_600 px -> 256^2 is 65_536 (too small), 512^2 = 262_144
    (0.0359, (2048, 2048), 512),
    # a whole atlas needs the whole atlas
    (1.0, (2048, 2048), 2048),
    # 16.5% of 2048^2 = 692_000 px -> 1024^2 = 1_048_576
    (0.165, (2048, 2048), 1024),
    # 0.04% of 2048^2 = 1_677 px -> 64^2 = 4_096
    (0.0004, (2048, 2048), 64),
    # tiny fragment still gets a usable minimum
    (0.0000001, (2048, 2048), 16),
    # non-square atlas: 4096x1024 = 4_194_304 px; 25% = 1_048_576 -> exactly 1024
    (0.25, (4096, 1024), 1024),
    # non-square atlas, small share: 2048x1024 = 2_097_152; 1% = 20_971 -> 256
    (0.01, (2048, 1024), 256),
    # coverage above 1.0 must not explode
    (2.0, (2048, 2048), 4096),
]

# Round-trip: the chosen texture must hold at least the pixels the object owned.
# Allow one halving, since a square texture cannot exactly match an arbitrary
# pixel count and the rule rounds up to the next power of two.
ETAIL_CASES = [
    (0.0359, (2048, 2048)),
    (0.165, (2048, 2048)),
    (0.5, (1024, 512)),
    (0.9, (3000, 2000)),
]


def main() -> int:
    failures = 0
    for coverage, atlas_size, expected in CASES:
        actual = recommended_resolution(coverage, atlas_size)
        ok = actual == expected
        failures += 0 if ok else 1
        print(
            f"SIZING coverage={coverage * 100:.4f}% atlas={atlas_size} "
            f"expected={expected} actual={actual} {'ok' if ok else 'FAIL'}"
        )

    for coverage, atlas_size in ETAIL_CASES:
        owned = coverage * atlas_size[0] * atlas_size[1]
        side = recommended_resolution(coverage, atlas_size)
        held = side * side
        ok = held >= owned
        failures += 0 if ok else 1
        print(
            f"ETAIL coverage={coverage * 100:.2f}% atlas={atlas_size} "
            f"owned={int(owned)} side={side} holds={held} "
            f"{'ok' if ok else 'FAIL'}"
        )

    print(f"SIZING failures={failures}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
