# Plan 001 — UV Repack

## Stack

- Blender 5.2 LTS, Python 3.11 (`blender.exe -b --factory-startup --python <script>`)
- Blender's own `bpy.ops.uv.pack_islands` as the packing engine
- `unittest` from the standard library as the test runner
- No third-party dependency, no `numpy`, no build step

## Why drive `pack_islands` instead of writing a packer

`pack_islands` is Blender's own production packer: it handles rotation, concave
island shapes, margin and normalisation, and it is what a user would get from
`U > Pack Islands`. Writing a rival packer would be a large surface area for
defects with no upside.

Its documented behaviour sets the design: it normalises islands **into the unit
tile**, so one call per object gives exactly "this object's islands fill this
object's UV space". It also only ever sees the active object's edit mesh, which
is what forces the one-object-at-a-time loop.

Engine variants were measured, not assumed, on the sample file (mean coverage
over 67 meshes):

| `shape_method` / `rotate_method` | Mean coverage |
|---|---|
| **CONCAVE / ANY (chosen)** | **52.72%** |
| CONVEX / ANY | 52.06% |
| CONCAVE / CARDINAL | 51.31% |
| AABB / ANY | 45.13% |

## Architecture

Layers depend inwards only. Nothing in `metrics` or `islands` knows that Blender
operators exist, so the geometry is testable without a scene.

```
uv_repack/
├── metrics.py     pure UV polygon geometry (areas, fanned triangles, bounds)
├── islands.py     Island value object; union-find grouping of polygons into islands
├── repack.py      MeshOutcome, PackReport, SkipPolicy; the pack loop
├── selection.py   which objects an operator acts on
├── api.py         repack(): validation + entry point, no operator context
├── operators.py   thin Blender adapter: read scene, call api, report
├── panel.py       N-panel, wires operators to buttons
├── __init__.py    register()/unregister(), scene settings
└── tests/run_tests.py
```

### Patterns used, and why

| Pattern | Where | Reason |
|---|---|---|
| Value object (frozen dataclass) | `Island`, `MeshOutcome`, `PackReport`, `SkipPolicy` | Results are derived facts. Frozen, so a report cannot be mutated after the run and assertions are meaningful. |
| Dependency inversion | `api.py` between `operators.py` and `repack.py` | The operator never packs. It reads scene state, calls the API and formats a report, so the packing path is reachable from a script and from tests without operator context. |
| Union-find | `islands.py` | Island grouping is a connectivity problem. Union-find makes it near-linear instead of a repeated flood fill. |
| Adapter / thin operator | `operators.py` | Blender operators cannot be unit-tested headlessly with context; keeping them free of logic moves the logic somewhere testable. |
| Policy object | `SkipPolicy` | "Is this mesh packed?" is a rule that grew a second clause. A named object with a predicate beats an inline `if` and is directly testable. |

### Island grouping

Corners are keyed by `(vertex_index, quantized_uv)`, then unioned. Two faces that
share a vertex also share the corner unless a seam split the UV, which is exactly
what distinguishes one island from two. Quantizing at `1e-6` welds Blender's
32-bit float UVs without merging genuinely distinct corners.

## Key decisions

**One `pack_islands` call per object.** The operator only sees the active object,
so targets are serialised through edit mode with a `try/finally` that always
restores object mode. A stuck edit session would otherwise block the next
object's `mode_set` and wedge the run.

**Skip needs two clauses.** `threshold` alone is insufficient. A single island
with a 1:4 aspect ratio caps at ~16% coverage no matter how well it is packed, so
a threshold-only rule would repack it on every run — and because `pack_islands`
is not bit-deterministic across runs, its UVs would drift each time. The
convergence clause compares against the gain recorded for that mesh datablock in
the previous run, held in a module-level map.

**Validation before mutation.** `api.repack` checks for an empty selection, for
meshes without UV layers, and for shared mesh datablocks before `pack_islands`
runs. Shared data is checked before the UV-layer filter, so linked duplicates are
refused even when they carry no UVs.

**No texture, no bake, no second UV layer.** Out of scope by user decision. Single
UV layer, overwritten in place.

## Test strategy

The suite runs headlessly against a real blend file rather than a fixture, because
the interesting failures only appear on real geometry.

Packing is expensive — a 2000-poly mesh takes seconds — so the default run packs a
bounded sample and `--all` packs every mesh. This is the difference between a
1.3-second suite and one that appears to hang.

Test names carry their requirement ID (`test_FR005_every_island_survives_the_repack`)
so coverage is checkable by grep rather than by reading a table.

## Known limitation

Achievable fill is bounded by island shape, not by the packer. Normalising a long
thin island's bounding box into the tile leaves the tile mostly empty. On the
sample file 55 of 67 meshes are a single elongated island and therefore land near
16%. Recovering that space would require splitting islands, which changes the
geometry of the unwrap and is deliberately out of scope.
