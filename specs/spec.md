# Spec 001 — UV Repack

**Status**: implemented, verified against `Untitled.blend`
**Scope**: repacking UV islands in place. No textures, no baking, no extra UV layers.

## User Scenarios & Testing

### P1 — Give a separated mesh its own UV space

*Why this priority*: this is the entire reason the addon exists. A model split
into many objects keeps the UV coordinates of the original shared atlas, so each
object wastes most of the tile and has unusably low texel density. Repacking the
object's own islands into the tile recovers that space without touching any other
object.

*Independent test*: select a mesh, press **Repack UVs** in the `UV Repack`
sidebar tab, and check its UV coverage rose.

**AC-1**
- Given a mesh whose UVs cover 0.04% of the tile
- When the user runs **Repack UVs** on it
- Then its coverage rises above 90% and its UVs stay inside 0..1

**AC-2**
- Given a selection of 67 separated meshes that each use a slice of one atlas
- When the user runs **Repack UVs** once
- Then every mesh's UVs are packed independently and each mesh's coverage increases

### P2 — Repacking never damages anything else

*Why this priority*: the operator acts on a selection inside a scene that holds
other objects. Silently rewriting a non-selected object's UVs — or corrupting a
mesh that is in edit mode — would be worse than not having the addon.

*Independent test*: pack one object and diff every other object's UV coordinates.

**AC-3**
- Given a mesh object that is not selected
- When the user repacks another object
- Then the unselected object's UV coordinates are unchanged, byte for byte

**AC-4**
- Given two objects sharing one mesh datablock
- When the user repacks them
- Then the operator unlinks them first, and the Python API refuses the call

### P3 — Re-running is cheap and idempotent

*Why this priority*: a user will press the button twice. The second press must
not degrade a previous result.

*Independent test*: run **Repack UVs** twice and compare UV coordinates.

**AC-5**
- Given meshes that were just repacked
- When the user runs **Repack UVs** again
- Then already-packed meshes keep identical UV coordinates

**AC-6**
- Given a mesh whose single island is too thin to ever fill the tile
- When the user repacks it twice
- Then it is not repacked again, because the last run barely improved it

## Edge Cases

| Case | Required behavior |
|---|---|
| Nothing selected | Operator reports "Select at least one mesh object", returns `CANCELLED` |
| Selection contains a mesh with no UV layer | API raises `ValueError` before writing anything |
| Mesh datablock shared by two selected objects | Operator unlinks; API raises `ValueError` |
| Mesh has faces but zero UV area | Packed; coverage stays 0 and no island is lost |
| A target is already in edit mode | Packed, and left in edit mode afterwards |
| `pack_islands` raises mid-run | No target is left in edit mode |

## Requirements

**FR-001**: The addon shall register itself and expose an N-panel named "UV Repack" in the 3D viewport sidebar.
**FR-002**: The addon shall ship as a package that Blender loads from `addons_core` without an install step.
**FR-003**: The panel shall display the number of selected mesh targets.
**FR-004**: When the user invokes **Repack UVs** with at least one mesh selected, the operator shall return `FINISHED`.
**FR-005**: The repack shall preserve the island count of every target.
**FR-006**: The repack shall keep every UV coordinate within 0..1.
**FR-007**: The repack shall increase the UV coverage of every target that is not already packed.
**FR-008**: When a target's UV coverage is below 1%, the repack shall increase its UV area by at least 5x.
**FR-009**: Where skip-if-packed is enabled, the repack shall leave a target's UVs unmodified when its coverage is at or above the configured threshold, or when the previous repack improved its coverage by less than the configured convergence delta.
**FR-010**: The repack shall not modify the UVs of any object outside the target list.
**FR-011**: If two targets share a mesh datablock, then the Python API shall raise `ValueError` before writing.
**FR-012**: If the target list is empty, then the Python API shall raise `ValueError`.
**FR-013**: If no target has a UV layer, then the Python API shall raise `ValueError`.
**FR-014**: If two targets share a mesh datablock, then the Python API shall raise `ValueError` regardless of whether they have UV layers.
**FR-015**: The operator shall leave every target out of edit mode after the run, including when packing fails.
**FR-016**: The operator shall report the target count and the mean coverage before and after.

## Key Entities

| Entity | Meaning |
|---|---|
| `Island` | One contiguous region of UV space, as a tuple of polygons |
| `MeshOutcome` | What happened to one mesh: island counts, coverage before/after, skipped |
| `PackReport` | All outcomes plus derived means, gains and a summary string |
| `SkipPolicy` | Threshold and convergence delta deciding whether to pack a mesh |

## Success Criteria

**SC-001**: A 67-mesh selection repacks end to end without a traceback.
**SC-002**: The median mesh in the sample file gains at least 100x its UV area.
**SC-003**: The bounded test suite completes in under 30 seconds.
**SC-004**: Packing settings survive in the scene, so a repack is repeatable.

## Assumptions

- Meshes are untextured. No image, material node or bake is read or written.
- One UV layer per mesh, overwritten in place. No second UV layer is created.
- Texel density is uniform across the input meshes, so per-object packing keeps
  that uniformity between objects.
- `uv.pack_islands` is the packing engine; achievable fill is bounded by island
  shape, and no attempt is made to split islands to fill the tile further.
