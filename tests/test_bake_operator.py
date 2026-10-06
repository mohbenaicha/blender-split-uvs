"""Exercise the Bake operator end to end, the way the N-panel button does.

Usage:
    blender -b --factory-startup --python tests/test_bake_operator.py -- <blend> [limit]
"""

import os
import sys

import bpy

ADDON_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ADDON_PARENT not in sys.path:
    sys.path.insert(0, ADDON_PARENT)

import addon_utils

addon_utils.enable("uv_repack", default_set=True)


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    blend = argv[0]
    limit = int(argv[1]) if len(argv) > 1 else 2

    bpy.ops.wm.open_mainfile(filepath=blend)
    addon_utils.enable("uv_repack", default_set=True)

    meshes = [ob for ob in bpy.context.view_layer.objects if ob.type == 'MESH']
    targets = meshes[:limit]
    scene = bpy.context.scene

    original_materials = {
        ob.name: [s.material.name for s in ob.material_slots] for ob in targets
    }

    # Exactly what the panel does: set the dropdown, then press the button.
    scene.uv_repack.bake_resolution = 'AUTO'
    scene.uv_repack.bake_margin = 8
    scene.uv_repack.skip_packed = False

    for ob in bpy.context.view_layer.objects:
        ob.select_set(ob in targets)
    bpy.context.view_layer.objects.active = targets[0]

    repack_result = bpy.ops.uv_repack.repack()
    bake_result = bpy.ops.uv_repack.bake()
    print(f"OPERATOR repack={repack_result} bake={bake_result}")

    baked = sorted(
        (i.name, i.size[0]) for i in bpy.data.images
        if i.name.startswith(tuple(t.name for t in targets))
    )
    for name, size in baked:
        print(f"OPERATOR_IMAGE {name} {size}px")

    unchanged = original_materials == {
        ob.name: [s.material.name for s in ob.material_slots] for ob in targets
    }
    print(f"OPERATOR_MATERIALS_UNCHANGED {unchanged}")

    leftover = [m.name for m in bpy.data.materials if m.name.startswith("UVREPACK_BAKE_")]
    print(f"OPERATOR_LEFTOVER_MATERIALS {len(leftover)}")

    ok = (
        repack_result == {'FINISHED'}
        and bake_result == {'FINISHED'}
        and unchanged
        and not leftover
        and len(baked) > 0
    )
    print(f"OPERATOR_OK {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
