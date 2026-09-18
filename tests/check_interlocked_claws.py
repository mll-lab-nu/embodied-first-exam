"""Original geometry, independent robot FK, and collision import contracts."""
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import json

from hydra import compose, initialize_config_dir
import mujoco
import numpy as np
import trimesh

from topogym.tasks.catalog import load_card
from topogym.tasks.interlocked_claws.geometry import ClawAssembly, generate_assets, geometry_report, reference_body_poses
from topogym.tasks.interlocked_claws.reference import ReferenceMotion
from topogym.tasks.interlocked_claws.reference_audit import point_motion_radii

ROOT = Path(__file__).resolve().parents[1]


class ClawChecks(unittest.TestCase):
    def test_exact_meshes_and_nonintersecting_reference_assembly(self):
        assembly = ClawAssembly()
        report = geometry_report(assembly)
        self.assertTrue(report["passed"])
        self.assertAlmostEqual(report["initial_surface_clearance_m"], .00505775659052, places=10)
        self.assertEqual([p["triangles"] for p in report["pieces"]], [14780, 14480])
        for b in assembly.bodies:
            self.assertFalse(b.mesh.is_convex)
            self.assertGreater(b.mesh.convex_hull.volume / b.mesh.volume, 3)
        # Positive collision control: putting an identical copy on itself collides.
        manager = trimesh.collision.CollisionManager()
        mesh = assembly.world_meshes()[0]
        manager.add_object("piece", mesh)
        self.assertTrue(manager.in_collision_single(mesh))

    def test_reference_transform_order_matches_independent_mujoco_fk(self):
        assembly = ClawAssembly()
        model = mujoco.MjModel.from_xml_path(str(ROOT / "assets/robots/aloha/aloha.xml"))
        data = mujoco.MjData(model)
        data.qpos[:] = assembly.reference["initial_qpos"]
        mujoco.mj_forward(model, data)
        poses = reference_body_poses(assembly.reference)
        for b in assembly.reference["bodies"][1:]:
            i = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, b["name"])
            self.assertGreaterEqual(i, 0)
            np.testing.assert_allclose(poses[b["id"]][:3, 3], data.xpos[i], atol=1e-12)
            np.testing.assert_allclose(poses[b["id"]][:3, :3], data.xmat[i].reshape(3, 3), atol=1e-12)

    def test_export_uses_same_nonconvex_triangles_for_visual_and_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            assembly, _ = generate_assets(tmp)
            for b in assembly.bodies:
                root = ET.parse(Path(tmp) / b.name / f"{b.name}.urdf").getroot()
                self.assertEqual(len(root.findall("link")), 1)
                self.assertEqual(root.findall("joint"), [])
                visual = root.find("link/visual/geometry/mesh").attrib["filename"]
                collision = root.find("link/collision/geometry/mesh").attrib["filename"]
                self.assertEqual(visual, collision)
                mesh = trimesh.load(Path(tmp) / b.name / visual, force="mesh", process=False)
                np.testing.assert_allclose(mesh.triangles, b.mesh.triangles, atol=1e-12)
                self.assertGreater(np.linalg.eigvalsh(b.mesh.moment_inertia).min(), 0)
            self.assertEqual(len(trimesh.load(Path(tmp) / "assembly.glb").geometry), 2)

    def test_local_tabletop_robot_removes_source_base_lift(self):
        from topogym.robot.assets import build_tabletop_aloha
        assembly = ClawAssembly()
        model = mujoco.MjModel.from_xml_path(str(build_tabletop_aloha()))
        data = mujoco.MjData(model)
        data.qpos[:] = assembly.reference["initial_qpos"]
        mujoco.mj_forward(model, data)
        poses = reference_body_poses(assembly.reference)
        for b in assembly.reference["bodies"][1:]:
            actual = data.body(b["name"])
            np.testing.assert_allclose(actual.xpos, poses[b["id"]][:3, 3]-[0, 0, .02], atol=1e-12)
            np.testing.assert_allclose(actual.xmat.reshape(3, 3), poses[b["id"]][:3, :3], atol=1e-12)

    def test_config_and_card_agree(self):
        with initialize_config_dir(config_dir=str(ROOT / "configs"), version_base="1.3"):
            cfg = compose(config_name="interlocked_claws_preview")
        self.assertEqual(cfg.task.variant, load_card("interlocked_claws")["baseline"]["asset_id"])
        self.assertEqual(cfg.robot_control.robot.name, "aloha")
        self.assertEqual(cfg.env.renderer.type, "nyx")
        self.assertEqual(cfg.env.presentation.background, "compact_lab")

    def test_physics_retains_source_robot_table_height(self):
        from topogym.robot.assets import build_tabletop_aloha
        with initialize_config_dir(config_dir=str(ROOT / "configs"), version_base="1.3"):
            cfg=compose(config_name="interlocked_claws_physics")
        self.assertEqual(cfg.robot_control.robot.base_riser_height_m,.02)
        model=mujoco.MjModel.from_xml_path(str(build_tabletop_aloha(cfg.robot_control.robot.base_riser_height_m)))
        data=mujoco.MjData(model);motion=ReferenceMotion()
        # These include the near-table dip that collided after lowering 20 mm.
        for t in (0,21,87.22,121.50472035082785,156.5):
            q,_,_,_,_=motion.sample(t);data.qpos[:]=q;mujoco.mj_forward(model,data)
            poses=reference_body_poses(motion.reference,q)
            for piece in motion.reference["pieces"]:
                body=motion.reference["bodies"][piece["gripper_body"]]
                np.testing.assert_allclose(data.body(body["name"]).xpos,poses[body["id"]][:3,3],atol=1e-12)

    def test_pinned_motion_release_is_continuous_and_tampering_rejected(self):
        motion=ReferenceMotion();self.assertEqual(len(motion.times),3084)
        self.assertEqual(len(motion.source["timeline"]),12)
        for i in range(1,len(motion.times)):
            if motion.source["held_mask"][i]!=motion.source["held_mask"][i-1]:
                before=motion.sample(motion.times[i]-1e-8)[2];after=motion.sample(motion.times[i])[2]
                np.testing.assert_allclose(before,after,atol=1e-9)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"altered.json";source=json.loads(motion.path.read_text());source["qpos"][0][0]+=.01
            path.write_text(json.dumps(source))
            with self.assertRaises(ValueError):ReferenceMotion(path)

    def test_continuous_bound_contains_actual_vertex_displacement(self):
        motion=ReferenceMotion();assembly=ClawAssembly();radii=point_motion_radii(assembly,motion)
        for t,delta in ((0,.01),(21,.02),(87,.02),(103,.01),(140,.01)):
            qa,_,pa,held,_=motion.sample(t);qb,_,pb,_,_=motion.sample(t+delta)
            for i,b in enumerate(assembly.bodies):
                a=b.mesh.vertices@pa[i][:3,:3].T+pa[i][:3,3]
                z=b.mesh.vertices@pb[i][:3,:3].T+pb[i][:3,3]
                measured=np.linalg.norm(a-z,axis=1).max()
                bound=np.sum(radii[i]*np.abs(qb-qa))*held[i]
                self.assertLessEqual(measured,bound+1e-12)


if __name__ == "__main__":
    unittest.main()
