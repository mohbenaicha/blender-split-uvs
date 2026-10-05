"""Python API: scriptable entry point that bypasses operator context."""

from .repack import MeshOutcome, PackReport, SkipPolicy, pack_uv_islands, uv_coverage

__all__ = ["repack", "MeshOutcome", "PackReport", "SkipPolicy", "uv_coverage"]


def repack(
    objects: list,
    margin: float = 0.001,
    skip_policy: SkipPolicy | None = None,
) -> PackReport:
    """Repack the given mesh objects' UVs in place. Returns the run's report.

    Fails before touching any mesh if a mesh datablock is shared, because
    repacking shared data would silently change objects the caller never passed
    in -- and Blender's re-entrant `pack_islands` would then pack the same mesh
    twice, corrupting the result.

    Meshes without a UV layer have nothing to pack and are filtered out, so a
    mixed selection is not an error.
    """
    meshes = [ob for ob in objects if ob.type == 'MESH' and ob.data.polygons]
    if not meshes:
        raise ValueError("no mesh objects to repack")
    if len({ob.data.name for ob in meshes}) != len(meshes):
        raise ValueError("targets share mesh data; run 'Object > Make Single User' first")
    targets = [ob for ob in meshes if ob.data.uv_layers.active]
    if not targets:
        raise ValueError("no mesh objects with a UV layer to repack")
    return pack_uv_islands(targets, margin, skip_policy)
