"""Grouping mesh polygons into UV islands."""

from dataclasses import dataclass

from .metrics import Point, bounds, polygons_area

# UVs closer than this are the same point. Blender floats are 32-bit, so a tight
# tolerance still welds corners that share a vertex but belong to different faces.
WELD_TOLERANCE = 1e-6


@dataclass(frozen=True)
class Island:
    """One contiguous region of UV space. Immutable: derived, never edited."""

    polygons: tuple[tuple[Point, ...], ...]

    @property
    def polygon_count(self) -> int:
        return len(self.polygons)

    @property
    def area(self) -> float:
        return polygons_area(list(self.polygons))

    @property
    def bounds(self) -> tuple[Point, Point]:
        return bounds(list(self.polygons))

    @property
    def bounding_area(self) -> float:
        low, high = self.bounds
        return (high.x - low.x) * (high.y - low.y)


def _group_polygons(polygons: list[list[Point]], keys: list[tuple]) -> list[Island]:
    """Union-find over polygon indices, joined where `keys` match."""
    parent = list(range(len(polygons)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_b] = root_a

    owner: dict[tuple, int] = {}
    for index, polygon_keys in enumerate(keys):
        for key in polygon_keys:
            if key in owner:
                union(owner[key], index)
            else:
                owner[key] = index

    groups: dict[int, list[int]] = {}
    for index in range(len(polygons)):
        groups.setdefault(find(index), []).append(index)

    return [
        Island(tuple(tuple(polygons[i]) for i in members))
        for members in groups.values()
    ]


def islands_from_mesh(mesh) -> list[Island]:
    """UV islands of a mesh's active UV layer.

    Corners are keyed by vertex, so two faces sharing a vertex also share the
    corner unless the UVs were split (a seam) -- which is exactly what makes
    them separate islands.
    """
    uv_layer = mesh.uv_layers.active
    if uv_layer is None or not mesh.polygons:
        return []

    uv_data = uv_layer.data
    polygons: list[list[Point]] = []
    keys: list[list[tuple]] = []
    for polygon in mesh.polygons:
        points = []
        polygon_keys = []
        for loop_index in polygon.loop_indices:
            uv = uv_data[loop_index].uv
            point = Point((uv.x, uv.y))
            points.append(point)
            vertex_index = mesh.loops[loop_index].vertex_index
            polygon_keys.append(
                (vertex_index, round(uv.x / WELD_TOLERANCE), round(uv.y / WELD_TOLERANCE))
            )
        polygons.append(points)
        keys.append(polygon_keys)

    return _group_polygons(polygons, keys)
