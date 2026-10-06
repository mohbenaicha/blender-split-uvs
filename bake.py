"""Bake the atlas through the packed UVs, one object at a time.

Five passes run per object: base color, normal, and the three channels of a
packed ORM map, which are then merged into one image.

Each pass gets a throwaway material built for it, assigned to the object for the
duration of the bake and removed afterwards. The artist's materials are never
rewired, so a failure cannot leave a scene modified -- and because the bake
target node is created first, it is the tree's active node by construction.
"""

from dataclasses import dataclass, field

import bpy

from .bake_material import BAKE_MATERIAL_PREFIX, build_pass_material, free_pass_material
from .bake_nodes import bake_settings, source_image_of
from .bake_passes import ALL_PASSES, ORM_PASSES
from .nodes import bake_size_guard


@dataclass
class ObjectBake:
    """What baking produced for one object."""

    name: str
    resolution: int
    images: dict = field(default_factory=dict)
    passes: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class BakeReport:
    results: tuple

    @property
    def baked(self) -> list:
        return [r for r in self.results if r.ok]

    @property
    def failures(self) -> list:
        return [r for r in self.results if not r.ok]

    def summary(self) -> str:
        if not self.results:
            return "Nothing to bake"
        total = sum(r.passes for r in self.baked)
        text = f"Baked {len(self.baked)}/{len(self.results)} objects, {total} passes"
        if self.failures:
            text += f", {len(self.failures)} failed"
        return text


def _select_only(target) -> None:
    for other in bpy.context.view_layer.objects:
        if other is not None:
            other.select_set(False)
    target.select_set(True)
    bpy.context.view_layer.objects.active = target


def _new_image(name: str, resolution: int, is_data: bool):
    image = bpy.data.images.new(
        name, width=resolution, height=resolution, alpha=False, float_buffer=False
    )
    image.colorspace_settings.name = "Non-Color" if is_data else "sRGB"
    image.use_fake_user = True
    return image


def _combine_orm(channels: list, destination) -> None:
    """Merge three greyscale bakes into one packed ORM image.

    Each channel bake wrote its scalar into every channel, so taking one
    component per source and writing it to R, G and B yields the packed layout.
    """
    width, height = destination.size
    count = width * height * 4
    planes = []
    for source in channels:
        buffer = [0.0] * count
        source.pixels.foreach_get(buffer)
        planes.append(buffer)

    out = [0.0] * count
    for index in range(0, count, 4):
        out[index] = planes[0][index]
        out[index + 1] = planes[1][index + 1]
        out[index + 2] = planes[2][index + 2]
        out[index + 3] = 1.0
    destination.pixels.foreach_set(out)


def bake_object(target, resolution: int, margin: int) -> ObjectBake:
    """Bake every pass for one object and return what was written."""
    result = ObjectBake(name=target.name, resolution=resolution)

    materials = [slot.material for slot in target.material_slots if slot.material]
    if not materials:
        result.error = "no material"
        return result
    if not target.data.uv_layers.active:
        result.error = "no UV layer"
        return result

    source_image = source_image_of(materials[0])
    if source_image is None:
        result.error = f"{materials[0].name}: no image texture to bake from"
        return result

    settings = bake_settings(bpy.context.scene)
    settings.margin = margin
    original_slots = [slot.material for slot in target.material_slots]
    previously_selected = [
        ob for ob in bpy.context.view_layer.objects if ob is not None and ob.select_get()
    ]
    uv_layer = target.data.uv_layers.active.name

    try:
        _select_only(target)
        for bake_pass in ALL_PASSES:
            if bake_pass.key == "orm_r":
                image = _new_image(
                    f"{target.name}_orm_r", resolution, is_data=True
                )
            elif bake_pass.key == "orm_g":
                image = _new_image(
                    f"{target.name}_orm_g", resolution, is_data=True
                )
            elif bake_pass.key == "orm_b":
                image = _new_image(
                    f"{target.name}_orm_b", resolution, is_data=True
                )
            else:
                image = _new_image(
                    f"{target.name}_{bake_pass.key}", resolution, is_data=bake_pass.is_data
                )

            material = build_pass_material(
                f"{BAKE_MATERIAL_PREFIX}{target.name}_{bake_pass.key}",
                source_image,
                image,
                bake_pass.channel,
            )
            for slot in target.material_slots:
                slot.material = material

            try:
                bpy.ops.object.bake(
                    type=bake_pass.bake_type,
                    pass_filter={'COLOR'} if bake_pass.bake_type == 'EMIT' else {'NONE'},
                    use_clear=True,
                    margin=margin,
                    margin_type='EXTEND',
                    use_selected_to_active=False,
                    target='IMAGE_TEXTURES',
                    save_mode='INTERNAL',
                    uv_layer=uv_layer,
                )
            finally:
                for slot, material_ in zip(target.material_slots, original_slots):
                    slot.material = material_

            # The pass material is scaffolding; keep only the image it wrote.
            material.node_tree.nodes["BAKE_TARGET"].image = None
            free_pass_material(material)

            result.images[bake_pass.key] = image.name
            result.passes += 1

        orm = _new_image(f"{target.name}_orm", resolution, is_data=True)
        _combine_orm([bpy.data.images[result.images[p.key]] for p in ORM_PASSES], orm)
        result.images["orm"] = orm.name
    except (RuntimeError, ValueError) as error:
        result.error = str(error).replace("Error: ", "").strip()
    finally:
        for slot, material in zip(target.material_slots, original_slots):
            slot.material = material
        for ob in previously_selected:
            if ob.name in bpy.data.objects:
                ob.select_set(True)

    return result


def bake_objects(targets: list, resolution: int, margin: int = 8) -> BakeReport:
    """Bake a whole selection, refusing sizes that would exhaust memory."""
    if not targets:
        raise ValueError("bake_objects requires at least one target")

    projected = bake_size_guard(resolution, len(targets))
    limit = 8 * 1024 ** 3
    if projected > limit:
        raise ValueError(
            f"{len(targets)} objects at {resolution}px would need about "
            f"{projected / 1024 ** 3:.1f} GB; lower the resolution or bake in batches"
        )

    return BakeReport(tuple(bake_object(ob, resolution, margin) for ob in targets))
