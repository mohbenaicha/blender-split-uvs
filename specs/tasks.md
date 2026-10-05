# Tasks 001 — UV Repack

Ordered work. Every task names the requirement it satisfies and the file it
touches. `[X]` records a completed step; the verification section records
evidence, not intent.

## Phase 1 — Setup

- [X] T001 Confirm Blender 5.2 headless invocation and probe `pack_islands`
      parameters and defaults (`scale`, `shape_method`, `rotate_method`, `margin_method`)
      _Requirements: FR-016 (engine choice), plan: engine decision_
- [X] T002 Measure the sample file: 67 meshes, 249 islands, 76.5% of the tile used,
      uniform texel density 1.323, mean 1.14% coverage per mesh
      _Requirements: plan: test strategy_

## Phase 2 — Foundational

- [X] T003 [P] Pure UV geometry: fanned triangles, polygon area, bounds
      — `uv_repack/metrics.py`
      _Requirements: FR-005, FR-007_
- [X] T004 [P] `Island` value object and union-find grouping keyed by
      `(vertex_index, quantized_uv)` — `uv_repack/islands.py`
      _Requirements: FR-005_
- [X] T005 Target selection helper, returning meshes in scene order
      — `uv_repack/selection.py`
      _Requirements: FR-003_
- [X] T006 Scene-persisted settings group and `register()`/`unregister()`
      — `uv_repack/__init__.py`
      _Requirements: FR-001, FR-002, SC-004_

## Phase 3 — P1: repack a mesh into its own UV space

- [X] T007 `MeshOutcome`, `PackReport`, `uv_coverage`, and the one-object-at-a-time
      pack loop with a `try/finally` restoring object mode — `uv_repack/repack.py`
      _Requirements: FR-004, FR-005, FR-006, FR-015, FR-016_
- [X] T008 `api.repack()` with pre-write validation — `uv_repack/api.py`
      _Requirements: FR-011, FR-012, FR-013, FR-014_
- [X] T009 `uv_repack.repack` operator, delegating to the API — `uv_repack/operators.py`
      _Requirements: FR-004, FR-016_
- [X] T010 N-panel with target count, Repack and Measure buttons, gear settings
      — `uv_repack/panel.py`
      _Requirements: FR-001, FR-003_

## Phase 4 — P2: isolation

- [X] T011 Test that a non-selected object's UVs are byte-identical after a repack
      _Requirements: FR-010, AC-3_
- [X] T012 Test that shared mesh data is rejected before any write
      _Requirements: FR-011, FR-014, AC-4_
- [X] T013 Test that the operator unlinks linked duplicates before packing
      _Requirements: FR-011, AC-4_

## Phase 5 — P3: idempotent re-runs

- [X] T014 `SkipPolicy` with threshold and convergence delta; record the last gain
      per mesh datablock — `uv_repack/repack.py`
      _Requirements: FR-009, AC-5, AC-6_
- [X] T015 Test that a second run leaves converged meshes byte-identical
      _Requirements: FR-009, AC-5_
- [X] T016 Test the convergence rule directly, including "never packed yet"
      _Requirements: FR-009, AC-6_

## Phase 6 — Polish

- [X] T017 `uv_repack.report` measure-only operator
      _Requirements: FR-003_
- [X] T018 Bounded default test scope plus `--all`, so the suite cannot appear to hang
      — `uv_repack/tests/run_tests.py`
      _Requirements: SC-003_
- [X] T019 README with install, usage, settings and honest limits
      — `uv_repack/README.md`
      _Requirements: SC-001_

## Verification

Measured, not intended.

| Check | Command | Result |
|---|---|---|
| Bounded suite | `blender -b --factory-startup --python uv_repack\tests\run_tests.py -- Untitled.blend` | 16 run, 0 failures, 0 errors, 2.0s |
| Full suite, 67 meshes | same with `--all` | 16 run, 0 failures, 0 errors, 44s |
| Coverage result | full run | mean 1.14% → 52.72% per mesh, median area gain 1673x, min 4.2x, max 4197x |

Requirement coverage. Cited by a `test_FRnnn` name: FR-001, FR-004, FR-005,
FR-006, FR-007, FR-008, FR-009, FR-010, FR-011, FR-012, FR-013, FR-014.

Not cited by an automated test:

| Req | Why not | Evidence instead |
|---|---|---|
| FR-002 | Package loading is environmental | Addon enables from `addons_core` in every run (`test_FR001_addon_enables` imports it the same way) |
| FR-003 | Panel label text is not worth a headless assertion | `test_FR001_panel_is_registered_in_the_sidebar` checks category, space and region |
| FR-015 | Edit-mode restoration is covered indirectly | `try/finally` in `repack.py`; the full 67-mesh run completes without a stuck edit session |
| FR-016 | Operator report text | `PackReport.summary()` is exercised by every full-run outcome |

## Phase 6: Convergence

Gaps found after the first "passing" run, each classified and closed.

| # | Gap | Class | Cause | Closed by |
|---|---|---|---|---|
| 1 | 9 tests passed while the reported metric was meaningless | `contradicts` | `PackReport` summed coverage across all meshes and compared it to `len(targets)`, so the "fill efficiency" assertion compared a quantity to itself | Replaced aggregate fields with per-mesh `MeshOutcome` and `mean_coverage_*` over packed meshes only |
| 2 | 55 of 67 meshes packed to under 70%, reported as a pass | `missing` | No test bounded achievable fill, and no one had checked what the packer can actually reach | Investigated: single elongated islands cap at ~16% by construction. Documented as a limitation in `plan.md` and the README rather than asserted away |
| 3 | Engine variant was never measured | `missing` | Assumed `CONCAVE` was best | Measured 4 variants; `CONCAVE`/`ANY` confirmed best at 52.72% |
| 4 | Suite packed all 67 meshes four times and appeared to hang | `unrelated` | No bound on test scope | Bounded `SAMPLE_SIZE` default with `--all` opt-in; suite went from minutes to 1.3s |
| 5 | Re-running the operator repacked thin-island meshes forever, drifting their UVs | `partial` | `SkipPolicy` had only a coverage threshold | Added convergence delta against the previous run's recorded gain (T014) |
| 6 | `uv.select_all` raised on a mesh with no UV layer, leaving a target in edit mode | `missing` | No degenerate-input path | `try/finally` mode restore (T007), skip in the pack loop, and explicit `ValueError` in `api.repack` |
| 7 | Dead `margin` operator property and a split docstring that broke the addon import | `unrelated` | Incomplete refactor when settings moved to the scene | Property removed, docstring repaired |
| 8 | `view_layer.objects` yielded `None` after an active object was removed, crashing every iteration in tests and the pack loop | `missing` | Assumed the collection only ever holds valid objects | `None` guards in `repack.py` and the test helpers |
| 9 | Two tests asserted against whatever state earlier tests had left behind | `contradicts` | Fixtures read live meshes that `RepackTestCase` had already packed | Deterministic fixture: copy the mesh, then `squeeze_uvs_into_corner` |

### Accepted, not fixed

- **58 of 67 meshes finish under 90% coverage.** Geometry-limited: a single
  elongated island cannot fill the tile once its bounding box is normalised.
  Splitting islands would change the unwrap and is out of scope. Documented in
  `plan.md` and the README rather than hidden behind a weaker assertion.
- **`pack_islands` is not bit-deterministic across runs.** Repacking an
  already-packed mesh can move coverage by a fraction of a percent, which is why
  the skip rule exists; it is not treated as a defect.
