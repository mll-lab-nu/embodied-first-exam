#!/usr/bin/env python3
"""Tool contracts and fault injection; this suite does not certify physical grasping."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from topogym.planning.calibration_tools.candidates import (candidate_config, candidate_trial,
    parameter_grid, validate_candidate, build_candidate)
from topogym.planning.calibration_tools.grasp_observation import GraspTrace, explain_grasp
from topogym.planning.calibration_tools.grasp_trials import (GraspTrial, PHASES, TrialMetrics,
    normalize_trial, target_point)
from topogym.planning.calibration_tools.grasp_sweep import GraspSweep
from topogym.planning.calibration_tools.inspection import EventWindows, triggered
from topogym.planning.calibration_tools.contracts import UnsupportedCapability


def trial():
    return dict(hand="right", target="part", phases=[dict(name=p, action={}, steps=1) for p in PHASES],
                criteria=dict(minimum_lift_m=.02, maximum_slip_m=.005, minimum_hold_s=.025))


def record(tick=0, height=0., tcp=None, branch=0, grasp=None):
    return dict(state=dict(episode_id="fixture", branch_id=branch, state_id=tick,
                          physics_step=tick, sim_time_s=tick*.025),
        robot={"right": dict(tcp_position_world_m=[0, 0, height] if tcp is None else tcp,
                             tcp_orientation_wxyz=[1, 0, 0, 0], finger_position_m=[.01, .01])},
        world=dict(bodies={"part": dict(position_m=[0, 0, height], quaternion_wxyz=[1, 0, 0, 0])},
                   grasp=grasp, ipc={}), targets={})


def grasp():
    return dict(config=dict(model="ipc_soft_band_v1", stable_time_s=.02, max_translation_error_m=.01,
        targets=[dict(entity="rope", max_strain_ratio=1.3, contact_distance_m=.006)]),
        hands={"right": dict(intent="close", phase="idle", binding=None, stable_time_s=0.,
                             rejection="no_bilateral_candidate")},
        admission={"right": dict(entity="rope", nearby_vertices=0, qualified_region_centers=0,
                                  max_material_edge_ratio=1.1)}, health={}, events=[], event_sequence=0)


class ObservationTests(unittest.TestCase):
    def test_explanation_is_passive_and_unknown_is_not_passed(self):
        raw = grasp(); before = deepcopy(raw)
        row = explain_grasp(raw, hand="right")["hands"]["right"]
        self.assertEqual(row["explanation"], "no_nearby_material_vertices")
        self.assertFalse(row["conditions"]["bilateral_region_count"]["satisfied"])
        self.assertAlmostEqual(row["conditions"]["material_edge_ratio"]["margin"], .2)
        self.assertIsNone(row["conditions"]["follow_error_m"]["satisfied"])
        self.assertEqual(raw, before)
        self.assertFalse(explain_grasp(None)["enabled"])

    def test_backend_reason_and_health_take_precedence(self):
        raw = grasp(); raw["admission"]["right"]["rejection"] = "material_strain_or_nonfinite"
        self.assertEqual(explain_grasp(raw)["hands"]["right"]["explanation"], "material_strain_or_nonfinite")
        raw["hands"]["right"].update(binding=dict(target=["rope", 10]), phase="holding", rejection=None)
        raw["health"]["right"] = dict(max_follow_error_m=.015, max_material_edge_ratio=1.4)
        gates = explain_grasp(raw)["hands"]["right"]["conditions"]
        self.assertFalse(gates["follow_error_m"]["satisfied"])
        self.assertFalse(gates["material_edge_ratio"]["satisfied"])

    def test_transient_events_survive_one_control_and_do_not_repeat(self):
        emitted=[]; trace=GraspTrace(lambda kind, **row: emitted.append(row))
        raw=grasp();raw["hands"]["right"]["rejection"]=None
        raw.update(events=[dict(sequence=1,event="acquired",hand="right")],event_sequence=1)
        trace.begin_control();trace.observe(record(1,grasp=raw));trace.observe(record(1,grasp=raw))
        raw.update(events=[dict(sequence=2,event="lost",hand="right")],event_sequence=2)
        trace.observe(record(2,grasp=raw))
        current=dict(grasp_events=trace.control_events)
        self.assertTrue(triggered("grasp_acquired",None,current))
        self.assertTrue(triggered("grasp_lost",None,current))
        self.assertFalse(triggered(dict(name="grasp_lost",hand="left"),None,current))
        self.assertEqual(len(emitted),2)
        trace.begin_control();trace.observe(record(3,grasp=raw))
        self.assertFalse(trace.control_events)
        raw.update(events=[dict(sequence=1,event="acquired",hand="right")],event_sequence=1)
        trace.observe(record(1,branch=1,grasp=raw))
        self.assertEqual(len(trace.control_events),1)

    def test_grasp_watch_has_durable_trigger_and_numerical_window(self):
        out=[]; windows=EventWindows(lambda kind, **row:out.append((kind,row)),durable_events=True)
        windows.watch(["grasp_rejected"],before_steps=1,after_steps=1)
        windows.push(dict(grasp_events=[]))
        windows.push(dict(grasp_events=[dict(name="grasp_rejected",hand="right")]))
        windows.push(dict(grasp_events=[]))
        self.assertEqual([x[0] for x in out],["event_window_triggered","event_window_progress","event_window"])


class TrialTests(unittest.TestCase):
    def test_invalid_later_phase_is_rejected_before_execution(self):
        value=trial();value["phases"][-1]["name"]="typo"
        with self.assertRaises(ValueError): normalize_trial(value)
        value=trial();value["phases"][-1]["steps"]=0
        with self.assertRaises(ValueError): normalize_trial(value)
        value=trial();value["criteria"]["minimum_hold_s"]=0
        with self.assertRaises(ValueError): normalize_trial(value)

    def test_measured_hold_not_assist_boolean_decides_criteria(self):
        metrics=TrialMetrics(normalize_trial(trial()),record())
        for i,p in enumerate(PHASES,1):
            metrics.begin(p);metrics.sample(record(i,height=.04 if p in {"lift","hold"} else 0.))
        result=metrics.summary(True)
        self.assertTrue(result["criteria_passed"])
        self.assertAlmostEqual(result["longest_qualified_hold_s"],.025)
        self.assertFalse(result["physical_release_verified"])
        self.assertFalse(metrics.summary(False)["criteria_passed"])

    def test_slip_breaks_hold_despite_object_lift(self):
        metrics=TrialMetrics(normalize_trial(trial()),record())
        for i,p in enumerate(PHASES,1):
            metrics.begin(p)
            metrics.sample(record(i,height=.04 if p in {"lift","hold"} else 0.,
                                  tcp=[.02,0,.04] if p=="hold" else None))
        self.assertFalse(metrics.summary(True)["criteria_passed"])
        self.assertAlmostEqual(metrics.summary(True)["maximum_hold_slip_m"],.02)

    def test_soft_target_keeps_material_indices(self):
        r=record();r["world"]["fem"]={"rope":dict(position_m=[[0,0,0],[0,0,1],[0,0,20]])}
        p,kind=target_point(r,dict(entity="rope",vertex_indices=[0,1]))
        self.assertEqual(p.tolist(),[0,0,.5]);self.assertEqual(kind,"fixed_vertex_set_centroid")
        with self.assertRaises(IndexError): target_point(r,dict(entity="rope",vertex_indices=[4]))

    def test_trial_uses_runner_and_preserves_partial_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            owner=SimpleNamespace(output=Path(tmp),env=SimpleNamespace(tick_record=lambda:record()),
                config=SimpleNamespace(enable_rgb=False),active_trial=None,cancelled=lambda:False,
                before_action=lambda action:None,tracking=SimpleNamespace(finish=lambda:None))
            def run_policy(**kwargs):
                for i in range(2):
                    kwargs["policy"].act(None)
                    owner.active_trial.tick(record(i+1),[])
                    owner.active_trial.transition()
                raise RuntimeError("injected runner failure")
            owner.runner=SimpleNamespace(run_policy=run_policy)
            runtime=GraspTrial(owner,trial())
            with self.assertRaisesRegex(RuntimeError,"injected"):
                runtime.run()
            saved=json.loads((runtime.folder/"report.json").read_text())
            self.assertEqual(saved["status"],"failed");self.assertEqual(saved["completed_controls"],2)
            self.assertFalse(saved["metrics"]["criteria_passed"])
            self.assertIsNone(owner.active_trial)


class CandidateTests(unittest.TestCase):
    def test_grid_and_action_changes_are_immutable(self):
        grid=parameter_grid({"materials.rope.friction_mu":[.3,.6],
                             "phase_actions.close.right.gripper_position_m":[.01,.012]})
        self.assertEqual(len(grid),4)
        value=trial(); before=deepcopy(value);changed=candidate_trial(value,grid[0])
        self.assertEqual(value,before)
        self.assertEqual(changed["phases"][1]["actions"][0]["right"]["gripper_position_m"],.01)
        self.assertEqual(changed["phases"][0]["actions"],[{}])
        with self.assertRaises(ValueError):parameter_grid({"config.grasp_assist":[{}],"config.grasp_assist.model":["none"]})
        with self.assertRaises(ValueError):parameter_grid({"materials.rope.E":list(range(129))})

    def test_candidate_validation_does_not_silently_change_backend(self):
        with self.assertRaises(ValueError):validate_candidate(dict(config=dict(compute_backend="cpu")))
        with self.assertRaises(ValueError):validate_candidate(dict(materials=dict(rope=dict(E=-1))))
        with self.assertRaises(ValueError):validate_candidate(dict(robot_material=dict(mass=1)))
        config=dict(enable_rgb=False,compute_backend="cpu")
        changed=candidate_config(config,dict(config=dict(physics_dt_s=.005)))
        self.assertEqual(changed["physics_dt_s"],.005);self.assertNotIn("physics_dt_s",config)

    def test_build_scope_restores_class_and_builder_on_error(self):
        from topogym.world.tabletop import StandardTabletopSceneBuilder
        from topogym.tasks.base import EntitySpec, TaskSpec
        class Task:
            def finalize_spec(self,spec,**kwargs):return spec
        env=SimpleNamespace(_task_class=Task);builder=StandardTabletopSceneBuilder.create
        spec=TaskSpec((EntitySpec("box","box",None,morph_options=dict(size=[.01,.01,.01])),))
        with self.assertRaisesRegex(RuntimeError,"after declaration"):
            with build_candidate(env,dict(primitive_masses_kg=dict(box=.068))) as report:
                changed=env._task_class().finalize_spec(spec)
                self.assertAlmostEqual(changed.entities[0].material["rho"]*1.e-6,.068)
                self.assertTrue(report["changes"])
                raise RuntimeError("after declaration")
        self.assertIs(env._task_class,Task);self.assertIs(StandardTabletopSceneBuilder.create,builder)


class SweepTests(unittest.TestCase):
    def test_serial_rebuilds_failure_and_comparison_artifacts(self):
        active=[]; seen=[]
        class Session:
            def __init__(self,cfg,output,candidate):
                assert not active
                active.append(self);seen.append((cfg,candidate));self.candidate=candidate
                output.mkdir();(output/"source_manifest.json").write_text('{"source":"fixed"}')
            def run_grasp_trial(self,spec):return spec
            def wait(self,op):
                if self.candidate["name"]=="bad":raise RuntimeError("injected worker error")
                return dict(status="completed",metrics=dict(criteria_passed=False,maximum_lift_m=.01))
            def close(self):active.remove(self)
            def status(self):return {}
        with tempfile.TemporaryDirectory() as tmp:
            with GraspSweep(dict(enable_rgb=False,compute_backend="cpu"),trial(),
                [dict(name="bad"),dict(name="good")],Path(tmp)/"sweep",_session_factory=Session) as sweep:
                result=sweep.wait(timeout_s=10)
                self.assertEqual(result["status"],"incomplete")
                self.assertEqual([c["status"] for c in result["cases"]],["failed","completed"])
                self.assertFalse(result["cases"][1]["result"]["metrics"]["criteria_passed"])
                self.assertTrue((sweep.output/"comparison.csv").exists())
        self.assertFalse(active);self.assertEqual(len(seen),2)

    def test_stop_on_error_includes_incomplete_trial_receipts(self):
        closed=[]
        class Session:
            def __init__(self,cfg,output,candidate):
                output.mkdir();(output/"source_manifest.json").write_text('{}')
                self.name=candidate["name"]
            def run_grasp_trial(self,spec):return spec
            def wait(self,op):return dict(status="incomplete",metrics=dict(criteria_passed=False))
            def close(self):closed.append(self.name)
            def status(self):return {}
        with tempfile.TemporaryDirectory() as tmp:
            with GraspSweep(dict(enable_rgb=False,compute_backend="cpu"),trial(),
                [dict(name=n) for n in ("a","b")],Path(tmp)/"sweep",continue_on_error=False,
                _session_factory=Session) as sweep:
                result=sweep.wait(timeout_s=10)
                self.assertEqual([c["status"] for c in result["cases"]],["incomplete","pending"])
                self.assertEqual(result["status"],"incomplete")
        self.assertEqual(closed,["a"])

    def test_source_change_stops_comparison(self):
        class Session:
            def __init__(self,cfg,output,candidate):
                output.mkdir();(output/"source_manifest.json").write_text(json.dumps(candidate))
            def run_grasp_trial(self,spec):return spec
            def wait(self,op):return dict(status="completed",metrics={})
            def close(self):pass
            def status(self):return {}
        with tempfile.TemporaryDirectory() as tmp:
            with GraspSweep(dict(enable_rgb=False,compute_backend="cpu"),trial(),
                [dict(name=n) for n in ("a","b","c")],Path(tmp)/"sweep",_session_factory=Session) as sweep:
                result=sweep.wait(timeout_s=10)
                self.assertEqual([c["status"] for c in result["cases"]],["completed","failed","pending"])

    def test_cancel_stops_next_candidate(self):
        running=threading.Event(); cancelled=threading.Event()
        class Session:
            def __init__(self,cfg,output,candidate):
                output.mkdir();(output/"source_manifest.json").write_text('{}')
            def run_grasp_trial(self,spec):running.set();return 1
            def wait(self,op):
                cancelled.wait(5);return dict(status="cancelled",metrics={})
            def cancel(self):cancelled.set()
            def close(self):pass
            def status(self):return {}
        with tempfile.TemporaryDirectory() as tmp:
            with GraspSweep(dict(enable_rgb=False,compute_backend="cpu"),trial(),
                [dict(name=n) for n in ("a","b")],Path(tmp)/"sweep",_session_factory=Session) as sweep:
                self.assertTrue(running.wait(5));sweep.cancel();result=sweep.wait(timeout_s=10)
                self.assertEqual(result["status"],"cancelled")
                self.assertEqual(result["cases"][1]["status"],"pending")


if __name__ == "__main__": unittest.main()
