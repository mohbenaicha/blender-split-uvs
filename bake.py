"""Bake the atlas through the packed UVs, one material slot at a time.

Five passes run per slot: base colour, normal, and the three channels of a
packed ORM map, which are merged into one image afterwards.

Each pass gets a throwaway material assigned to the slot for the duration of the
bake. The artist's materials are never rewired, so a failure cannot leave a
scene modified, and the images written are the only lasting product.
"""

from dataclasses import dataclass, field

import bpy
import numpy

from .bake_material import (
    BAKE_MATERIAL_PREFIX,
    build_pass_material,
    build_result_material,
    free_pass_material,
    orm_channels_are_separate,
)
from .bake_nodes import bake_settings, source_image_of
from .bake_passes import ALL_PASSES, ORM_PASSES
from .nodes import bake_size_guard


@dataclass
class SlotBake:
    """What baking produced for one material slot."""

    slot_index: int
    source_material: str
    resolution: int
    images: dict = field(default_factory=dict)
    passes: int = 0


@dataclass
class ObjectBake:
    """What baking produced for one object."""

    name: str
    resolution: int
    slots: tuple = ()
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def passes(self) -> int:
        return sum(slot.passes for slot in self.slots)

    @property
    def images(self) -> dict:
        """Pass key to image name, flattened. Only meaningful for one slot."""
        if len(self.slots) != 1:
            return {}
        return dict(self.slots[0].images)


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
    """Create a generated image with the right colour space.

    The colour space is set here, while the image is still empty. Assigning a
    colour space to an image that already holds pixels frees those pixels, so
    this must never be done after a bake has written into the image.
    """
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
    Numpy does this without materialising four million Python floats.
    """
    first = numpy.empty(len(channels[0].pixels), dtype=numpy.float32)
    channels[0].pixels.foreach_get(first)
    planes = [first.reshape(-1, 4)]

    for channel in channels[1:]:
        buffer = numpy.empty(len(channel.pixels), dtype=numpy.float32)
        channel.pixels.foreach_get(buffer)
        planes.append(buffer.reshape(-1, 4))

    out = numpy.empty_like(planes[0])
    out[:, 0] = planes[0][:, 0]
    out[:, 1] = planes[1][:, 1]
    out[:, 2] = planes[2][:, 2]
    out[:, 3] = 1.0
    destination.pixels.foreach_set(out.reshape(-1))


def _pass_image_name(target_name: str, slot_index: int, slot_count: int, key: str) -> str:
    """Name a baked image after its object and, when it matters, its slot."""
    if slot_count > 1:
        return f"{target_name}_slot{slot_index}_{key}"
    return f"{target_name}_{key}"


def bake_slot(target, slot_index: int, resolution: int, margin: int) -> SlotBake:
    """Bake every pass for one material slot of one object."""
    from .repack import SOURCE_UV_LAYER, packed_uv_layer

    source_material = target.material_slots[slot_index].material
    result = SlotBake(
        slot_index=slot_index,
        source_material=source_material.name if source_material else "",
        resolution=resolution,
    )

    source_image = source_image_of(source_material)
    if source_image is None:
        raise ValueError(f"{source_material.name}: no image texture to bake from")

    # Read the atlas through the pre-repack mapping, write through the packed one.
    source_uv_layer = (
        SOURCE_UV_LAYER if target.data.uv_layers.get(SOURCE_UV_LAYER) else None
    )
    uv_layer = packed_uv_layer(target.data)
    if uv_layer is None:
        raise ValueError(f"{target.name}: no UV layer to bake into")
    slot_count = len(target.material_slots)
    originals = [slot.material for slot in target.material_slots]
    keep_debug = getattr(bpy.context.scene.uv_repack, "keep_bake_passes", False)

    def assign(material) -> None:
        target.material_slots[slot_index].material = material

    for bake_pass in ALL_PASSES:
        image = _new_image(
            _pass_image_name(target.name, slot_index, slot_count, bake_pass.key),
            resolution,
            is_data=bake_pass.is_data,
        )
        material = build_pass_material(
            f"{BAKE_MATERIAL_PREFIX}{target.name}_{slot_index}_{bake_pass.key}",
            source_image,
            image,
            bake_pass.channel,
            source_uv_layer,
        )
        assign(material)
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
            assign(originals[slot_index])
            free_pass_material(material)

        result.images[bake_pass.key] = image.name
        result.passes += 1

    orm = _new_image(
        _pass_image_name(target.name, slot_index, slot_count, "orm"),
        resolution,
        is_data=True,
    )
    channel_images = [bpy.data.images.get(result.images[p.key]) for p in ORM_PASSES]
    _combine_orm(channel_images, orm)
    result.images["orm"] = orm.name

    # The three channel bakes are now redundant: their values live in `orm`.
    if not keep_debug:
        for bake_pass in ORM_PASSES:
            channel = bpy.data.images.get(result.images.pop(bake_pass.key, ""))
            if channel is not None:
                channel.use_fake_user = False
                if channel.users == 0:
                    bpy.data.images.remove(channel)

    return result


def bake_object(target, resolution: int, margin: int) -> ObjectBake:
    """Bake every material slot of one object, then wire the results in."""
    result = ObjectBake(name=target.name, resolution=resolution)

    materials = [slot.material for slot in target.material_slots if slot.material]
    if not materials:
        result.error = "no material"
        return result
    if not target.data.uv_layers.active:
        result.error = "no UV layer"
        return result

    scene = bpy.context.scene
    engine_before = scene.render.engine
    settings = bake_settings(scene)
    settings.margin = margin
    previously_selected = [
        ob for ob in bpy.context.view_layer.objects if ob is not None and ob.select_get()
    ]

    slot_indices = [
        index for index, slot in enumerate(target.material_slots) if slot.material
    ]
    try:
        _select_only(target)
        slots = []
        for slot_index in slot_indices:
            slots.append(bake_slot(target, slot_index, resolution, margin))
        result.slots = tuple(slots)

        # Leave the object looking the way it did: bake results wired in.
        for slot_bake in result.slots:
            source = bpy.data.materials.get(slot_bake.source_material)
            material = build_result_material(
                f"{target.name}{'_slot' + str(slot_bake.slot_index) if len(slot_indices) > 1 else ''}_repacked",
                slot_bake.images,
                orm_channels_are_separate(source),
            )
            if material is not None:
                target.material_slots[slot_bake.slot_index].material = material
    except (RuntimeError, ValueError) as error:
        result.error = str(error).replace("Error: ", "").strip()
    finally:
        scene.render.engine = engine_before
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
