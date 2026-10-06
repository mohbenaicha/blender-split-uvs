bl_info = {
    "name": "UV Repack",
    "author": "mohbenaicha",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > UV Repack",
    "description": "Repack each selected mesh's UV islands so they fill their own UV tile",
    "category": "UV",
}

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty

from . import operators, panel

MODULES = (operators, panel)


class UVRepackSettings(bpy.types.PropertyGroup):
    """Panel state, persisted with the scene so a repack is repeatable."""

    margin: FloatProperty(
        name="Margin",
        description="Space left between islands, as a fraction of the tile",
        default=0.001,
        min=0.0,
        max=0.1,
        precision=4,
        subtype='FACTOR',
    )
    make_single_user: BoolProperty(
        name="Unlink Shared Meshes",
        description="Give linked duplicates their own mesh data so repacking one does not change the others",
        default=True,
    )
    skip_packed: BoolProperty(
        name="Skip Well-Packed Meshes",
        description="Leave meshes whose UVs already fill the tile alone, so re-running is safe",
        default=True,
    )
    threshold: FloatProperty(
        name="Skip Above",
        description="Coverage at or above which a mesh is considered already packed",
        default=0.90,
        min=0.0,
        max=1.0,
        precision=2,
        subtype='FACTOR',
    )
    converged_delta: FloatProperty(
        name="Converged Gain",
        description=(
            "Treat a mesh as packed when the last run improved its coverage by less than this, "
            "which stops thin islands being repacked forever"
        ),
        default=0.01,
        min=0.0,
        max=1.0,
        precision=3,
        subtype='FACTOR',
    )
    show_settings: BoolProperty(
        name="Settings",
        description="Show packing settings",
        default=False,
    )
    bake_resolution: EnumProperty(
        name="Texture Size",
        description="Resolution of the texture baked for each object",
        items=(
            ('256', "256 x 256", "Smallest; only for tiny fragments"),
            ('512', "512 x 512", "Loses detail on objects using over 6% of the atlas"),
            ('1024', "1024 x 1024", "Fits objects using up to 25% of the atlas"),
            ('2048', "2048 x 2048", "Preserves everything the atlas had"),
            ('AUTO', "Auto per Object", "Size each object to keep its current texel density"),
        ),
        default='AUTO',
    )
    bake_margin: IntProperty(
        name="Bake Margin",
        description="Padding around each island in pixels; too small causes seams",
        default=8,
        min=0,
        max=64,
    )
    keep_bake_passes: BoolProperty(
        name="Keep Pass Textures",
        description=(
            "Also keep the temporary ORM channel bakes instead of only the merged "
            "image. Uses four times the texture memory; for debugging only"
        ),
        default=False,
    )


CLASSES = (UVRepackSettings,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.uv_repack = bpy.props.PointerProperty(type=UVRepackSettings)
    for module in MODULES:
        for cls in module.CLASSES:
            bpy.utils.register_class(cls)


def unregister():
    for module in reversed(MODULES):
        for cls in reversed(module.CLASSES):
            bpy.utils.unregister_class(cls)
    del bpy.types.Scene.uv_repack
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
