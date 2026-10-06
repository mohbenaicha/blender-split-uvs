"""One repack run per target, plus the per-mesh numbers that prove it worked."""

from dataclasses import dataclass

import bpy

from .islands import Island, islands_from_mesh
from .metrics import polygons_area


# Repacking overwrites the UV layer, but a bake still has to know where each
# surface point sits in the ORIGINAL atlas. That mapping is preserved under this
# name before packing, and the bake's source image nodes read from it.
SOURCE_UV_LAYER = "UVRepack_Original"


def ensure_source_uv_layer(mesh) -> str | None:
    """Guarantee a UV layer holding the pre-repack atlas mapping.

    Returns the layer's name, or None when the mesh has no UVs at all.

    On a first run the active layer is duplicated under `SOURCE_UV_LAYER` so the
    mapping survives. On later runs that copy is left alone -- re-copying the
    packed UVs over it would destroy the very mapping it exists to protect.
    """
    if mesh.uv_layers.get(SOURCE_UV_LAYER) is not None:
        return SOURCE_UV_LAYER
    if mesh.uv_layers.active is None:
        return None
    # Blender would rename a duplicate to avoid the clash, so give the active
    # layer a temporary name first.
    mesh.uv_layers.active.name = "UVRepack_Packed_tmp"
    copied = mesh.uv_layers.new(name=SOURCE_UV_LAYER, do_init=True)
    if copied is None:
        return None
    return copied.name


def packed_uv_layer(mesh) -> str | None:
    """The layer a bake should write into: the active one, unless it is the backup."""
    active = mesh.uv_layers.active
    if active is None:
        return None
    if active.name == SOURCE_UV_LAYER and len(mesh.uv_layers) > 1:
        return next(
            (l.name for l in mesh.uv_layers if l.name != SOURCE_UV_LAYER), None
        )
    return active.name


@dataclass(frozen=True)
class MeshOutcome:
    """What happened to a single mesh."""

    name: str
    islands_before: int
    islands_after: int
    coverage_before: float
    coverage_after: float
    skipped: bool

    @property
    def islands_preserved(self) -> bool:
        return self.islands_before == self.islands_after

    @property
    def area_gain(self) -> float:
        if self.coverage_before <= 0.0:
            return 0.0
        return self.coverage_after / self.coverage_before

    @property
    def ok(self) -> bool:
        return self.islands_preserved


@dataclass(frozen=True)
class PackReport:
    """Outcome of a whole run. Frozen so it can be shown, logged or asserted on."""

    outcomes: tuple[MeshOutcome, ...]

    @property
    def packed(self) -> list[MeshOutcome]:
        return [o for o in self.outcomes if not o.skipped]

    @property
    def mean_coverage_before(self) -> float:
        packed = self.packed
        return sum(o.coverage_before for o in packed) / len(packed) if packed else 0.0

    @property
    def mean_coverage_after(self) -> float:
        packed = self.packed
        return sum(o.coverage_after for o in packed) / len(packed) if packed else 0.0

    @property
    def worst_coverage_after(self) -> float:
        return min((o.coverage_after for o in self.outcomes), default=0.0)

    @property
    def all_islands_preserved(self) -> bool:
        return all(o.ok for o in self.outcomes)

    @property
    def median_area_gain(self) -> float:
        packed = sorted(o.area_gain for o in self.packed)
        return packed[len(packed) // 2] if packed else 0.0

    def summary(self) -> str:
        if not self.outcomes:
            return "Nothing to repack"
        packed = self.packed
        if not packed:
            return f"All {len(self.outcomes)} meshes already well packed - nothing changed"
        return (
            f"Repacked {len(packed)}/{len(self.outcomes)} meshes: "
            f"coverage {self.mean_coverage_before * 100:.1f}% -> "
            f"{self.mean_coverage_after * 100:.1f}% per mesh "
            f"(median {self.median_area_gain:.0f}x area gain)"
        )


@dataclass(frozen=True)
class SkipPolicy:
    """When a mesh can be left alone instead of packed again.

    `threshold` alone is not enough: an island that is long and thin can never
    reach the threshold, so it would be repacked on every run and its UVs would
    drift each time. `converged_delta` catches exactly that case -- if the last
    pack barely moved the coverage, packing again will not help either.
    """

    threshold: float = 0.90
    converged_delta: float = 0.01

    def satisfied_by(self, coverage: float, previous_gain: float | None) -> bool:
        """`previous_gain` is None for a mesh that has not been packed yet."""
        if coverage >= self.threshold:
            return True
        return previous_gain is not None and previous_gain < 1.0 + self.converged_delta


# Gain each mesh datablock achieved on its last pack, so a second run can tell
# "this converged" from "this was never packed". Keyed by mesh name, which is
# stable within a session; a re-imported mesh simply gets packed once more.
_LAST_GAIN: dict[str, float] = {}


def uv_coverage(islands: list[Island]) -> float:
    """Area of UV space the islands' triangles occupy, in tile units (max 1.0)."""
    return polygons_area([list(p) for island in islands for p in island.polygons])


def pack_uv_islands(
    targets: list,
    margin: float,
    skip_policy: SkipPolicy | None = None,
) -> PackReport:
    """Repack each target's UVs so its islands fill the unit tile.

    Each object is packed on its own: `uv.pack_islands` only ever sees the edit
    mesh of the active object, so targets are isolated by entering and leaving
    edit mode once per object.

    With a `skip_policy`, meshes already packed well enough are left untouched,
    which makes re-running the operator cheap and idempotent.
    """
    if not targets:
        raise ValueError("pack_uv_islands requires at least one target")

    view_layer = bpy.context.view_layer
    active_before = view_layer.objects.active
    outcomes = []

    for target in targets:
        islands_before = islands_from_mesh(target.data)
        if not islands_before:
            # No UV layer, or no faces: nothing to pack, and uv.select_all would
            # fail its poll. Record the mesh as seen-but-skipped.
            outcomes.append(MeshOutcome(target.name, 0, 0, 0.0, 0.0, skipped=True))
            continue
        coverage_before = uv_coverage(islands_before)

        if skip_policy is not None and skip_policy.satisfied_by(
            coverage_before, _LAST_GAIN.get(target.data.name)
        ):
            outcomes.append(
                MeshOutcome(target.name, len(islands_before), len(islands_before),
                            coverage_before, coverage_before, skipped=True)
            )
            continue

        for other in view_layer.objects:
            if other is not None:
                other.select_set(False)
        target.select_set(True)
        view_layer.objects.active = target

        # Capture the atlas mapping before anything moves, so a later bake can
        # still read the source texture at the right coordinates.
        ensure_source_uv_layer(target.data)

        was_edit = target.mode == 'EDIT'
        try:
            if not was_edit:
                bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.uv.select_all(action='SELECT')
            bpy.ops.uv.pack_islands(
                udim_source='CLOSEST_UDIM',
                rotate=True,
                rotate_method='ANY',
                scale=True,
                merge_overlap=False,
                shape_method='CONCAVE',
                margin_method='SCALED',
                margin=margin,
            )
        finally:
            # Never leave a target in edit mode: a stuck edit session blocks the
            # next object's mode_set and can wedge the whole run.
            if not was_edit and target.mode == 'EDIT':
                bpy.ops.object.mode_set(mode='OBJECT')

        islands_after = islands_from_mesh(target.data)
        coverage_after = uv_coverage(islands_after)
        if coverage_before > 0.0:
            _LAST_GAIN[target.data.name] = coverage_after / coverage_before
        outcomes.append(
            MeshOutcome(target.name, len(islands_before), len(islands_after),
                        coverage_before, coverage_after, skipped=False)
        )

    if active_before is not None and active_before.name in bpy.data.objects:
        view_layer.objects.active = active_before

    return PackReport(tuple(outcomes))
