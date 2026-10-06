"""N-panel UI. Only wires existing operators to buttons."""

import bpy

from . import selection


class UVREPACK_PT_panel(bpy.types.Panel):
    bl_label = "UV Repack"
    bl_idname = "UVREPACK_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "UV Repack"

    def draw(self, context):
        layout = self.layout
        targets = selection.selected_meshes()

        if not targets:
            layout.label(text="Select mesh objects", icon='INFO')
            return

        settings = context.scene.uv_repack
        layout.label(text=f"Targets: {selection.describe(len(targets))}", icon='MESH_DATA')

        column = layout.column(align=True)
        column.scale_y = 1.4
        column.operator("uv_repack.repack", icon='UV')

        bake = layout.box()
        bake.label(text="Bake Textures", icon='TEXTURE')
        bake.prop(settings, "bake_resolution", text="")
        bake.prop(settings, "bake_margin")
        bake.operator("uv_repack.bake", icon='RENDER_STILL')

        row = layout.row(align=True)
        row.operator("uv_repack.report", icon='INFO')
        row.prop(settings, "show_settings", text="", icon='PREFERENCES')

        if settings.show_settings:
            box = layout.box()
            box.prop(settings, "skip_packed")
            if settings.skip_packed:
                box.prop(settings, "threshold")
                box.prop(settings, "converged_delta")
            box.prop(settings, "margin")
            box.prop(settings, "make_single_user")


CLASSES = (UVREPACK_PT_panel,)
