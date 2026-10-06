"""What a bake pass reads, and how the image it writes should be interpreted.

A pass is a value object: one bake call, one output channel layout. Keeping the
data out of the loop means the loop has no per-pass branching, and the pass
table can be inspected without a scene.
"""

from dataclasses import dataclass

EMIT = 'EMIT'
NORMAL = 'NORMAL'


@dataclass(frozen=True)
class BakePass:
    """One bake call per object."""

    key: str
    label: str
    bake_type: str
    channel: str | None  # None = emit the whole RGB value
    is_data: bool  # True -> Non-Color; False -> sRGB

    @property
    def colorspace(self) -> str:
        return "Non-Color" if self.is_data else "sRGB"


BASE_COLOR = BakePass("basecolor", "Base Color", EMIT, None, is_data=False)
NORMAL_MAP = BakePass("normal", "Normal", NORMAL, None, is_data=True)
ORM_RED = BakePass("orm_r", "ORM Red (AO)", EMIT, "Red", is_data=True)
ORM_GREEN = BakePass("orm_g", "ORM Green (Roughness)", EMIT, "Green", is_data=True)
ORM_BLUE = BakePass("orm_b", "ORM Blue (Metallic)", EMIT, "Blue", is_data=True)

# The three ORM channels are separate bakes because Blender bakes one scalar per
# pixel; they are merged back into a single image afterwards.
ORM_PASSES = (ORM_RED, ORM_GREEN, ORM_BLUE)
ALL_PASSES = (BASE_COLOR, NORMAL_MAP) + ORM_PASSES
