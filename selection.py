"""Choosing which objects an operator acts on.

Editing UVs is a mesh-edit operation, so target selection is deliberately an
*object* concern that must be decided before the packer runs, not inside it.
"""

import bpy


def selected_meshes() -> list:
    """Mesh objects in the current selection, in scene order."""
    selected = {ob.name for ob in bpy.context.selected_objects}
    return [
        ob
        for ob in bpy.context.view_layer.objects
        if ob.name in selected and ob.type == 'MESH' and ob.data.polygons
    ]


def describe(count: int) -> str:
    return f"{count} mesh{'es' if count != 1 else ''}"
