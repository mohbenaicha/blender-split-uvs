"""Proof that UV Repack works, run against a real blend file.

Usage:
    blender -b --factory-startup --python tests/run_tests.py -- <path-to.blend> [--all]

Packing is expensive (a 2000-poly mesh takes seconds), so by default only a
representative sample of meshes is packed. Pass --all to run every mesh in the
file, which is the real acceptance test but takes minutes.

Every test name carries the requirement it verifies (FR-nnn) so traceability is
mechanical rather than a spreadsheet.
"""

import os
import sys
import unittest

import bpy

ADDON = "uv_repack"
MARGIN = 0.001
SKIP_ABOVE = 0.90
SAMPLE_SIZE = 8  # small enough to finish fast, spread across the coverage range

# This file lives inside the addon package (tests/run_tests.py), so the package's
# parent directory has to be importable before `import uv_repack` resolves.
ADDON_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_ALL = False  # set by main() when --all is passed


def enable_addon() -> None:
    if ADDON_PARENT not in sys.path:
        sys.path.insert(0, ADDON_PARENT)
    import addon_utils

    addon_utils.enable(ADDON, default_set=True)


def select_only(objects) -> None:
    for ob in bpy.context.view_layer.objects:
        if ob is not None:
            ob.select_set(False)
    for ob in objects:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objects[0] if objects else None


def real_meshes() -> list:
    # view_layer.objects can yield None after an active object is removed, so
    # every iteration must tolerate it rather than assume a valid object.
    return [
        ob
        for ob in bpy.context.view_layer.objects
        if ob is not None
        and ob.type == 'MESH'
        and ob.data.polygons
        and ob.data.uv_layers.active
    ]


def sample_meshes(all_meshes: list) -> list:
    """A spread across the file: skip the heaviest mesh, then take an even stride.

    Sorting by polygon count and striding keeps the sample representative of the
    coverage range without packing every object, which is what made the suite slow.
    """
    if len(all_meshes) <= SAMPLE_SIZE:
        return list(all_meshes)
    ordered = sorted(all_meshes, key=lambda ob: len(ob.data.polygons))
    heaviest_excluded = ordered[:-1]
    stride = len(heaviest_excluded) / SAMPLE_SIZE
    return [heaviest_excluded[int(index * stride)] for index in range(SAMPLE_SIZE)]


def uvs_of(objects) -> dict:
    """Every UV coordinate of every given object, keyed for exact comparison."""
    return {
        ob.name: [
            (round(d.uv.x, 7), round(d.uv.y, 7)) for d in ob.data.uv_layers.active.data
        ]
        for ob in objects
    }


def all_uvs(ob) -> list:
    return [d.uv for d in ob.data.uv_layers.active.data]


class RegistrationTestCase(unittest.TestCase):
    """FR-001: the addon registers itself and exposes an N-panel named UV Repack."""

    def test_FR001_addon_enables(self):
        enable_addon()
        self.assertIn(ADDON, bpy.context.preferences.addons)

    def test_FR001_panel_is_registered_in_the_sidebar(self):
        from uv_repack.panel import UVREPACK_PT_panel

        self.assertEqual(UVREPACK_PT_panel.bl_category, "UV Repack")
        self.assertEqual(UVREPACK_PT_panel.bl_space_type, 'VIEW_3D')
        self.assertEqual(UVREPACK_PT_panel.bl_region_type, 'UI')

    def test_FR001_operators_are_registered(self):
        self.assertTrue(hasattr(bpy.ops.uv_repack, "repack"))
        self.assertTrue(hasattr(bpy.ops.uv_repack, "report"))
        self.assertAlmostEqual(bpy.context.scene.uv_repack.margin, 0.001)
        self.assertTrue(bpy.context.scene.uv_repack.skip_packed)


class RepackTestCase(unittest.TestCase):
    """FR-004..FR-008: the repack operator runs headlessly on a real multi-mesh selection."""

    @classmethod
    def setUpClass(cls):
        enable_addon()
        from uv_repack.islands import islands_from_mesh
        from uv_repack.repack import uv_coverage

        all_meshes = real_meshes()
        if not all_meshes:
            raise unittest.SkipTest("no UV-mapped meshes in this blend file")

        cls.total_in_file = len(all_meshes)
        cls.targets = all_meshes if RUN_ALL else sample_meshes(all_meshes)
        cls.islands_before = [islands_from_mesh(ob.data) for ob in cls.targets]
        cls.coverage_before = [uv_coverage(i) for i in cls.islands_before]
        cls.flagged = [b >= SKIP_ABOVE for b in cls.coverage_before]

        select_only(cls.targets)
        bpy.context.scene.uv_repack.margin = MARGIN
        cls.result = bpy.ops.uv_repack.repack()

        cls.islands_after = [islands_from_mesh(ob.data) for ob in cls.targets]
        cls.coverage_after = [uv_coverage(i) for i in cls.islands_after]

    def test_FR004_operator_finishes_on_multi_object_selection(self):
        self.assertEqual(self.result, {'FINISHED'})
        self.assertGreater(len(self.targets), 1)

    def test_FR005_every_island_survives_the_repack(self):
        for ob, before, after in zip(self.targets, self.islands_before, self.islands_after):
            self.assertEqual(
                len(before), len(after),
                f"{ob.name}: island count changed {len(before)} -> {len(after)}",
            )

    def test_FR006_repacked_uvs_stay_inside_the_unit_tile(self):
        for ob in self.targets:
            for uv in all_uvs(ob):
                self.assertGreaterEqual(round(uv.x, 5), 0.0, f"{ob.name} u below 0")
                self.assertGreaterEqual(round(uv.y, 5), 0.0, f"{ob.name} v below 0")
                self.assertLessEqual(round(uv.x, 5), 1.0, f"{ob.name} u above 1")
                self.assertLessEqual(round(uv.y, 5), 1.0, f"{ob.name} v above 1")

    def test_FR007_meshes_needing_repack_gain_coverage(self):
        checked = 0
        for ob, before, after, flagged in zip(
            self.targets, self.coverage_before, self.coverage_after, self.flagged
        ):
            if flagged:
                continue  # already packed; skipping is verified separately
            checked += 1
            self.assertGreater(
                after, before,
                f"{ob.name}: coverage did not improve ({before:.6f} -> {after:.6f})",
            )
        self.assertGreater(checked, 0, "no mesh in this file needed repacking")

    def test_FR008_gain_is_substantial_on_a_sparse_atlas(self):
        """A mesh using under 1% of the tile must gain at least 5x its area."""
        gains = [
            after / before
            for before, after, flagged in zip(
                self.coverage_before, self.coverage_after, self.flagged
            )
            if not flagged and before < 0.01
        ]
        self.assertGreater(len(gains), 0)
        for gain in gains:
            self.assertGreater(gain, 5.0, f"sparse mesh gained only {gain:.1f}x")


class SkipPackedTestCase(unittest.TestCase):
    """FR-009: meshes that already fill the tile are left byte-for-byte alone."""

    def test_FR009_skip_leaves_uvs_untouched(self):
        from uv_repack.api import repack
        from uv_repack.repack import SkipPolicy

        targets = real_meshes()
        if not targets:
            self.skipTest("no UV-mapped meshes")
        targets = targets if RUN_ALL else sample_meshes(targets)[:3]
        policy = SkipPolicy(SKIP_ABOVE, 0.01)
        before = uvs_of(targets)

        # First pass packs everything; second pass must reuse what pack_islands
        # already got right rather than drifting it.
        repack(targets, MARGIN, policy)
        after_first = uvs_of(targets)
        report = repack(targets, MARGIN, policy)
        after_second = uvs_of(targets)

        self.assertNotEqual(before, after_first, "first pass changed nothing")

        skipped = [o.name for o in report.outcomes if o.skipped]
        self.assertTrue(skipped, "second pass skipped nothing, so nothing was converged")
        for name in skipped:
            self.assertEqual(
                after_first[name], after_second[name], f"{name}: skipped yet changed"
            )

    def test_FR009_converged_meshes_are_not_repacked_forever(self):
        """A mesh that cannot reach the threshold must still stop being packed."""
        from uv_repack.repack import SkipPolicy

        policy = SkipPolicy(threshold=0.90, converged_delta=0.01)
        self.assertTrue(policy.satisfied_by(0.95, None), "above threshold")
        self.assertTrue(policy.satisfied_by(0.15, 1.001), "converged")
        self.assertFalse(policy.satisfied_by(0.15, None), "never packed yet")
        self.assertFalse(policy.satisfied_by(0.15, 5.0), "still improving")


def squeeze_uvs_into_corner(ob, factor: float = 0.05) -> None:
    """Shrink a mesh's UVs into the tile's bottom-left corner, like a shared atlas."""
    for data in ob.data.uv_layers.active.data:
        data.uv = (data.uv.x * factor, data.uv.y * factor)


class IsolationTestCase(unittest.TestCase):
    """FR-010/FR-011: a repack must never touch an object outside the targets."""

    def setUp(self):
        enable_addon()
        self.bystander = bpy.data.objects.new(
            "bystander", bpy.data.meshes.new("bystander")
        )
        bpy.context.scene.collection.objects.link(self.bystander)
        self.bystander.data.from_pydata(
            [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [], [(0, 1, 2, 3)]
        )
        self.bystander.data.uv_layers.new(name="UVMap")
        for index, uv in enumerate([(0.9, 0.9), (0.95, 0.9), (0.95, 0.95), (0.9, 0.95)]):
            self.bystander.data.uv_layers.active.data[index].uv = uv

    def tearDown(self):
        bpy.data.objects.remove(self.bystander, do_unlink=True)

    def test_FR010_other_objects_keep_their_uvs_exactly(self):
        target = real_meshes()[0]
        before = uvs_of([self.bystander])
        select_only([target])
        bpy.context.scene.uv_repack.margin = MARGIN
        bpy.ops.uv_repack.repack()
        self.assertEqual(before, uvs_of([self.bystander]))

    def test_FR011_shared_mesh_data_is_rejected_before_any_write(self):
        from uv_repack.api import repack

        twin = bpy.data.objects.new("bystander_twin", self.bystander.data)
        bpy.context.scene.collection.objects.link(twin)
        try:
            before = uvs_of([self.bystander, twin])
            with self.assertRaises(ValueError):
                repack([self.bystander, twin], MARGIN)
            self.assertEqual(before, uvs_of([self.bystander, twin]))
        finally:
            bpy.data.objects.remove(twin, do_unlink=True)

    def test_FR011_operator_unlinks_shared_meshes_then_packs_them(self):
        """The operator path resolves sharing by unlinking, unlike the strict API."""
        from uv_repack.islands import islands_from_mesh
        from uv_repack.repack import uv_coverage

        # Copy the source mesh and squeeze its UVs into a corner, so the fixture
        # starts sparse regardless of what earlier tests already packed.
        source = real_meshes()[0]
        shared = source.data.copy()
        first = bpy.data.objects.new("linked_a", shared)
        twin = bpy.data.objects.new("linked_b", shared)
        for ob in (first, twin):
            bpy.context.scene.collection.objects.link(ob)
        try:
            squeeze_uvs_into_corner(first)
            before = uv_coverage(islands_from_mesh(twin.data))

            select_only([first, twin])
            settings = bpy.context.scene.uv_repack
            settings.make_single_user = True
            settings.skip_packed = False
            settings.margin = MARGIN
            result = bpy.ops.uv_repack.repack()

            self.assertEqual(result, {'FINISHED'})
            self.assertIsNot(first.data, twin.data, "meshes were not unlinked")
            self.assertGreater(
                uv_coverage(islands_from_mesh(twin.data)), before,
                "twin was not repacked",
            )
        finally:
            for ob in (first, twin):
                if ob.name in bpy.data.objects:
                    bpy.data.objects.remove(ob, do_unlink=True)


class DegenerateInputTestCase(unittest.TestCase):
    """FR-012/FR-013/FR-014: bad input is refused rather than corrupting a scene."""

    def make_mesh(self, name, with_uvs=True):
        ob = bpy.data.objects.new(name, bpy.data.meshes.new(name))
        bpy.context.scene.collection.objects.link(ob)
        ob.data.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [], [(0, 1, 2, 3)])
        if with_uvs:
            ob.data.uv_layers.new(name="UVMap")
        return ob

    def test_FR012_empty_selection_raises(self):
        from uv_repack.api import repack

        with self.assertRaises(ValueError):
            repack([], MARGIN)

    def test_FR013_mesh_without_uv_layer_yields_no_work(self):
        from uv_repack.api import repack

        bare = self.make_mesh("no_uvs", with_uvs=False)
        try:
            with self.assertRaises(ValueError):
                repack([bare], MARGIN)
        finally:
            bpy.data.objects.remove(bare, do_unlink=True)

    def test_FR014_shared_data_is_rejected_even_without_uvs(self):
        from uv_repack.api import repack

        bare = self.make_mesh("shared_no_uvs", with_uvs=False)
        twin = bpy.data.objects.new("shared_no_uvs_twin", bare.data)
        bpy.context.scene.collection.objects.link(twin)
        try:
            with self.assertRaises(ValueError) as caught:
                repack([bare, twin], MARGIN)
            self.assertIn("share mesh data", str(caught.exception))
        finally:
            bpy.data.objects.remove(twin, do_unlink=True)
            bpy.data.objects.remove(bare, do_unlink=True)


def main() -> int:
    global RUN_ALL
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    RUN_ALL = "--all" in argv
    paths = [a for a in argv if not a.startswith("--")]

    enable_addon()
    if paths:
        bpy.ops.wm.open_mainfile(filepath=paths[0])
        enable_addon()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite(
        loader.loadTestsFromTestCase(case)
        for case in (
            RegistrationTestCase,
            RepackTestCase,
            SkipPackedTestCase,
            IsolationTestCase,
            DegenerateInputTestCase,
        )
    )
    result = unittest.TextTestRunner(verbosity=1).run(suite)

    case = RepackTestCase
    if getattr(case, "coverage_before", None):
        before = case.coverage_before
        after = case.coverage_after
        gains = sorted(a / b for b, a in zip(before, after) if b)
        print(
            f"\nRESULT meshes={len(case.targets)}/{case.total_in_file} "
            f"mean={sum(before) / len(before) * 100:.2f}%->{sum(after) / len(after) * 100:.2f}% "
            f"median_gain={gains[len(gains) // 2]:.0f}x "
            f"min_gain={gains[0]:.1f}x max_gain={gains[-1]:.0f}x "
            f"under90={sum(1 for a in after if a < 0.90)}/{len(after)}"
        )
    print(f"TESTS run={result.testsRun} failures={len(result.failures)} errors={len(result.errors)}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
