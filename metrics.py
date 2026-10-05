"""UV polygon-area metrics.

Pure geometry: operates on (vertex_count, uv) pairs so it has no dependency on
Blender data structures beyond mathutils, and can be exercised without a scene.
"""

from mathutils import Vector

Point = Vector
Triangle = tuple[Point, Point, Point]


def corner_winding(uvs: list[Point]) -> list[Triangle]:
    """Fan-triangulate a polygon's UV corners.

    Convex polygons give exact triangles. Concave polygons give signed
    over/under-counts that cancel in the sum, so totals stay correct.
    """
    return [(uvs[0], uvs[i], uvs[i + 1]) for i in range(1, len(uvs) - 1)]


def triangle_area(a: Point, b: Point, c: Point) -> float:
    return abs((b - a).cross(c - a)) * 0.5


def polygon_area(uvs: list[Point]) -> float:
    return sum(triangle_area(*t) for t in corner_winding(uvs))


def polygons_area(polygons: list[list[Point]]) -> float:
    return sum(polygon_area(uvs) for uvs in polygons)


def bounds(polygons: list[list[Point]]) -> tuple[Point, Point]:
    points = [uv for uvs in polygons for uv in uvs]
    return (
        Vector((min(p.x for p in points), min(p.y for p in points))),
        Vector((max(p.x for p in points), max(p.y for p in points))),
    )
