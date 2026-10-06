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


class UVREPACK_OT_bake(bpy.types.Operator):
    """Bake the original textures through the packed UVs, one texture per object"""

    bl_idname = "uv_repack.bake"
    bl_label = "Bake Textures"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return bool(selection.selected_meshes())

    def execute(self, context):
        from .bake import BakeReport, bake_object, bake_objects
        from .bake_nodes import source_image_of
        from .islands import islands_from_mesh
        from .nodes import recommended_resolution
        from .repack import uv_coverage

        targets = selection.selected_meshes()
        if not targets:
            self.report({'ERROR'}, "Select at least one mesh object")
            return {'CANCELLED'}

        settings = context.scene.uv_repack
        try:
            if settings.bake_resolution == 'AUTO':
                # Size each object to keep the texel density it already had.
                atlas = _atlas_size(targets, source_image_of)
                outcomes = []
                for target in targets:
                    coverage = uv_coverage(islands_from_mesh(target.data))
                    size = recommended_resolution(coverage, atlas)
                    outcomes.append(bake_object(target, size, settings.bake_margin))
                report = BakeReport(tuple(outcomes))
            else:
                report = bake_objects(
                    targets, int(settings.bake_resolution), settings.bake_margin
                )
        except ValueError as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}

        if report.failures:
            first = report.failures[0]
            self.report({'ERROR'}, f"{first.name}: {first.error}")
            return {'CANCELLED'}

        self.report({'INFO'}, report.summary())
        return {'FINISHED'}


def _atlas_size(targets, source_image_of) -> tuple[int, int]:
    """Pixel dimensions of the atlas being resampled, used to size the outputs."""
    for target in targets:
        for slot in target.material_slots:
            if slot.material is None:
                continue
            image = source_image_of(slot.material)
            if image is not None and image.size[0] > 0:
                return (image.size[0], image.size[1])
    return (2048, 2048)


CLASSES = (UVREPACK_OT_repack, UVREPACK_OT_report, UVREPACK_OT_bake)
