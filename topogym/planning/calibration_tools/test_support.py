"""Development tool contracts; no task tuning or physics-success claims.

Run with python -B -m topogym.planning.calibration_tools.test_support -v.
"""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

import numpy as np

from .task_summary import summarize_task
from .run_comparison import compare_runs, summarize_run
from .contact_geometry import contacts, surface_distance, gripper_geometry
from .object_drives import ObjectDrives, declare_force, force_command
from .contracts import UnsupportedCapability


class TaskSummaryTests(unittest.TestCase):
    def test_progress_enablement_and_acceptance_are_separate(self):
        info = dict(task_success=False, task_terminated=False, goal_evaluation_complete=True,
            evaluation_status="available", support=dict(status="integrated", validation="some report", gaps=[]))
        result = summarize_task(info, dict(goal_active=True, stable_time_s=.1, result=dict(metrics={"goal": True})))
        self.assertTrue(result["progress"]["goal_active"])
        self.assertFalse(result["progress"]["task_success"])
        self.assertTrue(result["evaluation"]["goal_enabled"])
        self.assertIsNone(result["qualification"]["accepted_scope"])

    def test_failure_time_limit_and_success_are_not_conflated(self):
        failed = summarize_task(dict(task_terminated=True, task_success=False, termination_reason="invalid_volume"), {})
        self.assertEqual(failed["outcome"]["failure_reason"], "invalid_volume")
        limited = summarize_task(dict(task_terminated=False, task_success=False, termination_reason="time_limit"), {})
        self.assertTrue(limited["outcome"]["time_limit"])
        self.assertFalse(limited["outcome"]["failed"])
        success = summarize_task(dict(task_terminated=True, task_success=True, termination_reason="Goal stable"), {}, exploration=True)
        self.assertIsNone(success["outcome"]["failure_reason"])
        self.assertFalse(success["formal_qualification"])

    def test_unknown_fields_remain_unknown(self):
        result = summarize_task({}, {})
        self.assertIsNone(result["progress"]["task_success"])
        self.assertIsNone(result["evaluation"]["goal_enabled"])


class RunComparisonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.a, self.b = [Path(self.tmp.name)/name for name in ("a", "b")]
        for p, seconds in ((self.a, 4.), (self.b, 2.)):
            (p/"execution").mkdir(parents=True)
            self.write(p/"session.json", dict(config=dict(task_id="x", seed=0, physics_dt_s=.01)))
            self.write(p/"source_manifest.json", {"source.py": "abc"})
            self.write(p/"execution/asset_manifest.json", {"part": "abc"})
            self.write(p/"timings.json", dict(costs=dict(control_step=dict(calls=2, failed_calls=0,
                seconds=seconds, self_seconds=seconds/2)), incomplete_spans=[]))
            events = [dict(kind="control_committed", action={"n": n}, physics_steps=2) for n in range(2)]
            events.append(dict(kind="plan_prepared", plan_id="one", selection="reused", timings=dict(check_s=.2)))
            (p/"events.jsonl").write_text("".join(json.dumps(e)+"\n" for e in events))
    def tearDown(self): self.tmp.cleanup()
    @staticmethod
    def write(path, value): path.write_text(json.dumps(value))
    def test_equal_recorded_workload_can_be_compared(self):
        result = compare_runs([self.a, self.b])
        self.assertEqual(result["comparisons"][0]["control_speedup"], 2.)
        self.assertEqual(result["runs"][0]["physics_ticks"], 4)
        self.assertEqual(result["planning_by_selection"]["reused"]["check_s"]["samples"], 2)
        self.assertFalse(result["hardware_and_background_load_verified"])
    def test_changed_config_and_source_do_not_get_speedup(self):
        self.write(self.b/"source_manifest.json", {"source.py": "changed"})
        result = compare_runs([self.a, self.b])["comparisons"][0]
        self.assertFalse(result["comparable"])
        self.assertIsNone(result["control_speedup"])
        self.assertIn("source", result["differences"])
    def test_rewind_changes_active_branch_but_not_wall_work(self):
        with (self.a/"events.jsonl").open("a") as stream:
            stream.write(json.dumps(dict(kind="restore_committed", action_count=1))+"\n")
        row = summarize_run(self.a)
        self.assertEqual((row["control_steps"], row["active_branch_steps"]), (2, 1))
    def test_torn_or_missing_evidence_is_not_a_speedup_claim(self):
        with (self.b/"events.jsonl").open("a") as stream: stream.write('{"kind":')
        result = compare_runs([self.a, self.b])["comparisons"][0]
        self.assertIn("incomplete_evidence", result["differences"])
        self.assertIsNone(result["control_speedup"])
    def test_failed_attempt_costs_are_visible(self):
        timing = json.loads((self.b/"timings.json").read_text())
        timing["costs"]["control_step"]["failed_calls"] = 1
        self.write(self.b/"timings.json", timing)
        self.assertIn("control_failed_calls", compare_runs([self.a,self.b])["comparisons"][0]["differences"])
    def test_same_hold_actions_with_different_forces_are_different_work(self):
        for path, force in ((self.a, 1.), (self.b, 2.)):
            with (path/"events.jsonl").open("a") as stream:
                stream.write(json.dumps(dict(kind="object_drive_command", force_world_n=[force,0,0], index=0))+"\n")
        comparison=compare_runs([self.a,self.b])["comparisons"][0]
        self.assertIn("execution_context", comparison["differences"])
        self.assertIsNone(comparison["control_speedup"])


class ContactTests(unittest.TestCase):
    def test_positions_stay_aligned_after_filtering(self):
        native = dict(link_a=np.array([1, -1, 2]), link_b=np.array([2, -1, 3]),
            force=np.ones((3, 3)), penetration=np.array([.001, 0, .002]),
            position=np.array([[1,0,0],[9,9,9],[2,0,0]]))
        entities = {name:NS(links=[NS(idx=i,name=name)]) for i,name in enumerate(("unused","robot","piece","table"))}
        env = NS(_world=NS(entities=entities, physics_step=4, scene=NS(sim=NS(coupler=NS(_ipc_world=object()),
            rigid_solver=NS(is_active=True,collider=NS(get_contacts=lambda **k:native))))))
        result = contacts(env, ["table"])
        self.assertEqual(len(result["contacts"]),1)
        self.assertEqual(result["contacts"][0]["contact_position_world_m"],[2,0,0])
        self.assertIsNone(result["ipc"]["contacts"])
        self.assertFalse(result["ipc"]["force_available"])

    def test_whole_surface_and_pad_patch_are_distinct(self):
        # Two slabs with a 10 mm gap, even though nominal finger coordinates say 20 mm.
        import trimesh
        left, right = [trimesh.creation.box([.01,.02,.02]) for _ in range(2)]
        right.apply_translation([.02,0,0])
        surfaces = {"finger_a":(left.vertices,left.faces,"fixture"), "finger_b":(right.vertices,right.faces,"fixture")}
        robot = NS(groups={"left":NS(grasp=NS(finger_links=("finger_a","finger_b")),gripper_field="gripper_position_m")},
            observe=lambda:{"left":{"finger_position_m":[.02,.02]}},
            capture_state=lambda:NS(targets={"left":{"gripper_position_m":.025}}))
        env = NS(_robot=robot,_world=NS(physics_step=0))
        with patch("topogym.planning.calibration_tools.contact_geometry.link_surface", side_effect=lambda env,name,source:surfaces[name]):
            result=gripper_geometry(env)["hands"]["left"]
            self.assertAlmostEqual(result["finger_surface_clearance"]["distance_m"],.01)
            self.assertIsNone(result["pad_surface_clearance"])
            exported=gripper_geometry(env,include_surfaces=True)["hands"]["left"]["surfaces"]
            np.testing.assert_array_equal(exported["finger_a"]["triangles"],left.faces)
            patches={"left":{name:list(range(len(mesh[1]))) for name,mesh in surfaces.items()}}
            result=gripper_geometry(env,pad_faces=patches)["hands"]["left"]
            self.assertAlmostEqual(result["pad_surface_clearance"]["distance_m"],.01)
            with self.assertRaises(ValueError): gripper_geometry(env,pad_faces={"left":{"finger_a":[999],"finger_b":[0]}})

    def test_intersection_is_not_a_force_or_depth_measurement(self):
        import trimesh
        mesh=trimesh.creation.box([1,1,1])
        other=mesh.copy(); other.apply_translation([.2,0,0])
        result=surface_distance((mesh.vertices,mesh.faces),(other.vertices,other.faces))
        self.assertTrue(result["surfaces_intersect"])
        self.assertIsNone(result["contact_force_n"])
        self.assertIsNone(result["penetration_depth_m"])


class DriveTests(unittest.TestCase):
    def owner(self):
        owner=NS(events=[],steps=0,poisoned=False)
        owner.evidence=NS(event=lambda kind,**values:owner.events.append(dict(kind=kind,**values)))
        owner.runner=NS(_last_tick={"world":{"bodies":{"piece":{"position_m":[0.,0.,0.],"linear_velocity_m_s":[0.,0.,0.]}},
                                           "fem":{"rope":{"position_m":np.zeros((4,3)),"velocity_m_s":np.zeros((4,3))}}}})
        owner.env=NS(_terminated=False,_truncated=False,_faulted=False,_checkpoint_current=lambda:None)
        owner.state_ref=lambda:{"state_id":owner.steps}
        owner.need_physics=lambda:None
        owner.cancelled=lambda:False
        def step(action):
            self.assertEqual(action,{})
            owner.steps+=1
            return dict(control_steps=1,physics_steps=10,reason="policy_done")
        owner.step=step
        return owner
    def driver(self,owner,kind="rigid"):
        driver=ObjectDrives(owner,{"piece":kind})
        driver.slots={"piece":dict(kind=kind)}
        driver.sent=[]
        driver.set_force=lambda name,force,indices:driver.sent.append(np.asarray(force).copy())
        driver.clear=lambda:driver.sent.append("cleared")
        return driver
    def test_force_is_bounded_and_control_steps_are_standard(self):
        owner=self.owner(); driver=self.driver(owner)
        result=driver.run("piece",control_steps=2,max_force_n=2,force_world_n=[1,0,0])
        self.assertEqual(owner.steps,2)
        self.assertEqual(driver.sent[-1],"cleared")
        self.assertTrue(all(row["intervention"] for row in owner.events))
        self.assertFalse(result["formal_qualification"])
    def test_position_following_clamps_force_without_teleport(self):
        owner=self.owner(); driver=self.driver(owner)
        driver.run("piece",control_steps=3,max_force_n=1,positions_world_m=[[10,0,0]])
        self.assertTrue(all(np.linalg.norm(v)<=1 for v in driver.sent[:-1]))
        self.assertEqual(owner.runner._last_tick["world"]["bodies"]["piece"]["position_m"],[0,0,0])
    def test_invalid_force_does_not_start_or_step(self):
        owner=self.owner(); driver=self.driver(owner)
        with self.assertRaises(ValueError): driver.run("piece",control_steps=1,max_force_n=1,force_world_n=[2,0,0])
        self.assertEqual(owner.events,[])
        self.assertEqual(owner.steps,0)
    def test_exception_clears_force_and_retains_error(self):
        owner=self.owner(); driver=self.driver(owner)
        def failure(action): raise RuntimeError("fixture failure")
        owner.step=failure
        with self.assertRaisesRegex(RuntimeError,"fixture failure"):
            driver.run("piece",control_steps=2,max_force_n=2,force_world_n=[1,0,0])
        self.assertEqual(driver.sent[-1],"cleared")
        self.assertEqual(owner.events[-1]["reason"],"execution_error")
    def test_cancellation_and_early_termination(self):
        owner=self.owner(); driver=self.driver(owner)
        owner.cancelled=lambda:True
        self.assertEqual(driver.run("piece",control_steps=2,max_force_n=2,force_world_n=[1,0,0])["reason"],"cancelled")
        self.assertEqual(owner.steps,0)
    def test_unprepared_object_is_explicitly_unsupported(self):
        owner=self.owner(); driver=self.driver(owner)
        with self.assertRaises(UnsupportedCapability): driver.run("other",control_steps=1,max_force_n=1,force_world_n=[0,0,0])
    def test_pd_force_units_and_bound(self):
        np.testing.assert_allclose(force_command(np.zeros(3),np.ones(3),np.ones(3),kp=3,kd=1,maximum=100),[2,2,2])


class NativeDeclarationTests(unittest.TestCase):
    """Real libuipc geometry/buffer API, no CUDA World or simulation."""
    def test_native_rigid_and_fem_force_buffers_and_clear(self):
        try:
            import uipc
        except ImportError:
            self.skipTest("pyuipc is absent; use the Nyx environment for native declarations")
        vertices=np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]],dtype=float)
        geometry=uipc.geometry.tetmesh(vertices,np.array([[0,1,2,3]],dtype=np.int32))
        _,attribute=declare_force(geometry,"fem")
        driver=ObjectDrives(NS(),{"rope":"fem"})
        driver.slots={"rope":dict(kind="fem",attribute=attribute)}
        driver.set_force("rope",np.array([4.,0,0]),[1,3])
        values=np.asarray(attribute.view()).reshape(-1,3)
        np.testing.assert_allclose(values.sum(0),[4,0,0])
        np.testing.assert_allclose(values[[0,2]],0)
        driver.clear(); np.testing.assert_allclose(values,0)
        mesh=uipc.geometry.trimesh(vertices,np.array([[0,2,1],[0,1,3],[0,3,2],[1,2,3]],dtype=np.int32))
        _,attribute=declare_force(mesh,"rigid")
        flags=mesh.instances().find("is_constrained")
        driver.slots={"piece":dict(kind="rigid",attribute=attribute,flags=flags)}
        driver.set_force("piece",np.array([1.,2,3]),None)
        np.testing.assert_allclose(np.asarray(attribute.view()).reshape(12)[:3],[1,2,3])
        self.assertEqual(np.asarray(flags.view()).item(),1)
        driver.clear()
        self.assertEqual(np.asarray(flags.view()).item(),0)


def summary_worker(pipe, cancel, config, output, session_id, kind):
    import os
    os.setsid()
    pipe.send(dict(kind="task_summary", summary={"progress":{"task_success":False}}))
    pipe.send(dict(kind="ready", progress={"stage":"idle"}))
    while True:
        request=pipe.recv()
        if request["method"] == "step_until":
            pipe.send(dict(kind="task_summary", summary={"state":{"control_step":7},"progress":{"task_success":False}}))
            cancel.wait(3)
        pipe.send(dict(kind="result",operation_id=request["operation_id"],result={"ok":True}))
        if request["method"] == "close": break
    pipe.close()


class SessionSummaryTests(unittest.TestCase):
    def test_summary_is_available_while_worker_is_busy(self):
        from .supervisor import Supervisor
        import time
        with tempfile.TemporaryDirectory() as directory:
            supervisor=Supervisor({},Path(directory)/"run",kind="geometry",worker_target=summary_worker)
            try:
                op=supervisor.submit("step_until")
                deadline=time.monotonic()+2
                while time.monotonic()<deadline:
                    current=supervisor.status(op)["progress"]["task_summary"]
                    if current and current.get("state",{}).get("control_step")==7: break
                    time.sleep(.01)
                self.assertEqual(current["state"]["control_step"],7)
                supervisor.cancel(op)
                self.assertTrue(supervisor.wait(op)["ok"])
            finally:
                supervisor.close()


if __name__ == "__main__":
    unittest.main()
