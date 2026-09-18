"""Independent packing, fixture compatibility and crossed-axis invariants."""
import unittest
from dataclasses import asdict

import numpy as np
from omegaconf import OmegaConf

from topogym.tasks.fiber_bundling.geometry import FiberLayout
from topogym.tasks.fiber_bundling.ring_mount import RingMount, require_fixture_evidence
from topogym.tasks.fiber_bundling.variants import rules, sample_parameters, candidate_config, inspect_candidate


class FiberVariantChecks(unittest.TestCase):
    def test_legacy_fixture_and_gate_are_preserved(self):
        cfg=OmegaConf.create(dict(geometry=asdict(FiberLayout())))
        self.assertEqual(RingMount.from_task_config(cfg).kind,"legacy_box_v1")
        part=RingMount().parts(FiberLayout(),(.35,0,.24),0)[-1]
        self.assertEqual(part[1],"box")
        np.testing.assert_allclose(part[3],(.012,.016,.2065),atol=1e-12)
        require_fixture_evidence(cfg,{})

    def test_new_support_and_changed_aperture_reject_old_evidence(self):
        cfg=OmegaConf.create(dict(geometry=asdict(FiberLayout()),ring_mount=dict(kind="thin_copper_rod_v1")))
        with self.assertRaises(RuntimeError): require_fixture_evidence(cfg,{})
        gate=dict(ring_fixture=RingMount.from_task_config(cfg).signature(FiberLayout()))
        require_fixture_evidence(cfg,gate)
        cfg.geometry.ring_inner_radius_m=.014
        with self.assertRaises(RuntimeError): require_fixture_evidence(cfg,gate)
        del cfg.ring_mount
        with self.assertRaises(RuntimeError): require_fixture_evidence(cfg,{})

    def test_thin_rod_seats_in_outer_wall_without_entering_hole(self):
        for radius in rules()["shared"]["representative_ring_radii_m"]:
            layout=FiberLayout(ring_inner_radius_m=radius)
            center=np.array([.35,0.,.24])
            name,kind,pos,size,_=RingMount(kind="thin_copper_rod_v1").parts(layout,center,0)[-1]
            self.assertEqual(kind,"cylinder")
            self.assertAlmostEqual(size[0]*2,.005)
            top=pos[2]+size[1]/2
            outer_bottom=center[2]-radius-2*layout.ring_tube_radius_m
            self.assertAlmostEqual(top-outer_bottom,.002)
            self.assertLess(top,center[2]-radius)
            self.assertAlmostEqual(pos[2]-size[1]/2,.012)

    def test_density_and_radius_are_independent_reproducible_axes(self):
        spec=rules()
        for seed in range(18):
            by_family=[sample_parameters(seed,f) for f in spec["families"]]
            self.assertEqual(len({p["ring_inner_radius_m"] for p in by_family}),1)
            for p in by_family:
                self.assertEqual(p,sample_parameters(seed,p["family_id"]))
                self.assertIn(p["fiber_count"],spec["families"][p["family_id"]]["fiber_counts"])
                self.assertEqual(p["shape_seed"],7)

    def test_crossed_representatives_do_not_change_wire_material_or_paths_with_aperture(self):
        spec=rules()
        for family_id,family in spec["families"].items():
            prior=None
            for radius in spec["shared"]["representative_ring_radii_m"]:
                cfg=candidate_config(dict(family_id=family_id,fiber_count=family["representative_count"],
                    ring_inner_radius_m=radius,shape_seed=7))
                layout=FiberLayout(**dict(cfg.task.geometry))
                paths=np.asarray(layout.fibers())
                if prior is not None: np.testing.assert_array_equal(prior,paths)
                prior=paths
                report=inspect_candidate(cfg)
                self.assertTrue(report["geometry_checks_passed"])
                self.assertFalse(report["full_threading_verified"])
                for key in ("trunk_radius_m","fiber_radius_m","fiber_length_m","fiber_damping","density_kg_m3"):
                    self.assertEqual(getattr(layout,key),getattr(FiberLayout(),key))
                # Independent nearest-root distances agree with the reported pitch.
                roots=paths[:,0,:]
                distances=np.linalg.norm(roots[:,None]-roots[None,:],axis=-1)
                np.fill_diagonal(distances,np.inf)
                self.assertAlmostEqual(distances.min(),report["root_center_spacing_m"])


if __name__=="__main__":
    unittest.main()
