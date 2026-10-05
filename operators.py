"""Operator layer: reads scene state, delegates to the API, reports the outcome."""

import bpy

from . import selection
from .api import repack
from .repack import SkipPolicy


class UVREPACK_OT_repack(bpy.types.Operator):
    """Repack the selected meshes' UV islands so each fills its own UV tile"""

    bl_idname = "uv_repack.repack"
    bl_label = "Repack UVs"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(selection.selected_meshes())

    def execute(self, context):
        targets = selection.selected_meshes()
        if not targets:
            self.report({'ERROR'}, "Select at least one mesh object")
            return {'CANCELLED'}

        settings = context.scene.uv_repack

        if settings.make_single_user and len({ob.data.name for ob in targets}) != len(targets):
            overrides = {"object": targets[0], "selected_editable_objects": targets}
            with context.temp_override(**overrides):
                bpy.ops.object.make_single_user(
                    type='SELECTED_OBJECTS', object=True, obdata=True
                )

        skip_policy = (
            SkipPolicy(settings.threshold, settings.converged_delta)
            if settings.skip_packed
            else None
        )
        try:
            report = repack(targets, settings.margin, skip_policy)
        except ValueError as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}

        if not report.all_islands_preserved:
            broken = [o.name for o in report.outcomes if not o.ok]
            self.report(
                {'WARNING'},
                f"Island count changed on {len(broken)} mesh(es): {', '.join(broken[:3])}",
            )
            return {'FINISHED'}

        self.report({'INFO'}, report.summary())
        return {'FINISHED'}


class UVREPACK_OT_report(bpy.types.Operator):
    """Measure the selected meshes' current UV usage without changing anything"""

    bl_idname = "uv_repack.report"
    bl_label = "Measure UVs"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return bool(selection.selected_meshes())

    def execute(self, context):
        targets = selection.selected_meshes()
        if not targets:
            self.report({'ERROR'}, "Select at least one mesh object")
            return {'CANCELLED'}

        from .islands import islands_from_mesh
        from .repack import uv_coverage

        coverages = [uv_coverage(islands_from_mesh(ob.data)) for ob in targets]
        mean = sum(coverages) / len(coverages)
        self.report(
            {'INFO'},
            f"{selection.describe(len(targets))}: UV coverage {mean * 100:.2f}% of the tile "
            f"on average (worst {min(coverages) * 100:.2f}%, best {max(coverages) * 100:.2f}%)",
        )
        return {'FINISHED'}


CLASSES = (UVREPACK_OT_repack, UVREPACK_OT_report)
