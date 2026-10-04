#!/usr/bin/env python3
"""The grading replays of the GPU families (rcb_topogym.py tooling v16, 2026-10-03): the hold after the last row, the
replay tolerances, the confirmation-window record, and that every other family and every non-grading replay is
unchanged. Session.replay itself runs on a scripted world (a real TaskDefinition's update, its stability window and
failure path); no Genesis, no physics: the lab replays in docs/rcb/benchmarks/topogym.md are the physical evidence."""
import contextlib
import importlib.util
import io
import os
import sys
import unittest
import warnings
from pathlib import Path
from types import SimpleNamespace

import numpy as np

os.environ["RCB_SESSION_LOG"] = ""
warnings.simplefilter("ignore", ResourceWarning)      # the graders' own json.load(open(...)) style
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "harbor_templates/topogym/common")]
import rcb_topogym as M  # noqa: E402
from topogym.tasks.base import TaskDefinition  # noqa: E402

DT = .0025                  # physics tick
TICKS = 10                  # per control step (40 Hz)
STABLE_S = .025             # a 10-tick confirmation window (the real tasks: 0.5 s = 200 ticks)
GPU = {"blanket_flatten", "knot_untying", "rope_threading", "slotted_post_ring", "orbits", "lock_picking"}


class CoverageTask(TaskDefinition):
    """blanket_flatten's goal shape: covered (coverage >= minimum_coverage_ratio), settled (the fastest particle at most
    maximum_speed_m_s) and still (displacement since the confirmation started at most maximum_drift_m); a scripted
    failure."""
    task_id = "grading_regression"
    defaults = dict(minimum_coverage_ratio=.95, maximum_speed_m_s=.03, maximum_drift_m=.003, stable_duration_s=STABLE_S)

    def evaluate_state(self, state):
        cfg, coverage, speed = self.config, state["coverage"], state.get("speed", 0.)
        reached = (coverage >= cfg["minimum_coverage_ratio"] and speed <= cfg["maximum_speed_m_s"]
                   and state.get("drift", 0.) <= cfg["maximum_drift_m"])
        return (reached, "Cloth fell below the table" if state.get("fell") else None,
                dict(coverage_ratio=coverage, maximum_speed_m_s=speed))


def scripted_session(family, coverage, fell_at=None, speed=lambda k: 0., drift=lambda k: 0.):
    """A Session without Genesis: the real replay() / _GradingReplay over a scripted world whose coverage at physics tick
    k is coverage(k). step() runs the env's tick loop (task.update per tick, the end at the first terminated tick)."""
    task = CoverageTask()
    task.initialize(dict(physics_step=0, coverage=coverage(0)))
    start = task.get_state()
    s = object.__new__(M.Session)
    s.task, s.env, s.control_hz, s.max_steps, s._video = family, SimpleNamespace(_task=task), 40., 10 ** 6, None
    world = dict(tick=0)

    def reset():
        task.set_state(start)
        world["tick"] = 0
        s.n_steps, s.episode_end, s.episode_done = 0, None, False

    def step(action, *, _physics_steps=None):
        if s.episode_end is not None:
            return True
        for _ in range(TICKS if _physics_steps is None else int(_physics_steps)):
            world["tick"] += 1
            k = world["tick"]
            result = task.update(dict(physics_step=k, coverage=coverage(k), speed=speed(k), drift=drift(k),
                                      fell=fell_at is not None and k >= fell_at), DT)
            if result.terminated:
                s.episode_end = "success" if result.task_success else result.reason
                break
        s.n_steps += 1
        return s.episode_end is not None

    s.reset, s.step = reset, step
    s.hold_action = lambda: np.zeros(3)
    s.success = lambda: bool(task.result.task_success)
    s.status = lambda: dict(success=s.success(), sim_steps=s.n_steps, episode_end=s.episode_end, physics_steps=world["tick"])
    reset()
    return s, task


ROWS = np.zeros((5, 3), dtype=np.float32)       # 5 rows = 50 ticks


class GradingReplay(unittest.TestCase):
    def test_the_table_is_the_six_gpu_families(self):
        self.assertEqual(set(M.REPLAY_TOLERANCES), GPU)
        cpu = {f for f, t in M.TASKS.items() if t["simulator"].get("compute_backend") == "cpu"}
        self.assertFalse(cpu & set(M.REPLAY_TOLERANCES))
        for fam, thresholds in M.REPLAY_TOLERANCES.items():
            for name, (path, side, slack) in thresholds.items():
                self.assertIn(name, M._GRADING_VALUES)
                self.assertIn(side, ("at_least", "at_most"))
                self.assertTrue(slack < 0 if side == "at_least" else slack > 0, (fam, name))    # always towards passing
        self.assertEqual(M.REPLAY_TOLERANCES["blanket_flatten"], {"coverage": ("minimum_coverage_ratio", "at_least", -.03),
                                                                  "particle_speed": ("maximum_speed_m_s", "at_most", .05)})
        self.assertEqual(M.GRADING_HOLD_S, 2.0)

    def test_a_success_within_the_rows_is_strict(self):
        s, task = scripted_session("blanket_flatten", lambda k: .96 if k >= 30 else .90)
        st = s.replay(ROWS, grading=True)
        g = st["grading"]
        self.assertTrue(st["success"])
        self.assertEqual(st["physics_steps"], 40)                     # the strict window: ticks 30..40 at 0.96 >= 0.95
        self.assertEqual((g["rows"], g["strict_success"], g["success_row"], g["hold_steps"]), (4, True, 4, 0))
        self.assertFalse(g["success_in_hold"] or g["tolerance_needed"])
        self.assertTrue(g["thresholds"]["coverage"]["live_held"])
        self.assertEqual(M.strict_goal([st]), (1, 4))

    def test_the_rows_use_the_instance_thresholds_and_only_the_hold_the_slack(self):
        s, task = scripted_session("blanket_flatten", lambda k: .94 if k >= 30 else .90)
        st = s.replay(ROWS, grading=True)
        g = st["grading"]
        self.assertTrue(st["success"])                                # 0.94 < 0.95: no success within the 5 rows
        self.assertEqual(st["physics_steps"], 61)                     # the hold at 0.93: a window from tick 51 to 61
        self.assertEqual((g["rows"], g["strict_success"], g["success_row"], g["hold_steps"], g["success_in_hold"]),
                         (5, False, None, 2, True))
        cov = g["thresholds"]["coverage"]
        self.assertEqual((cov["live"], cov["replay"], cov["window_ticks"]), (.95, .92, 11))
        self.assertAlmostEqual(cov["window_worst"], .94)
        self.assertFalse(cov["live_held"])
        self.assertTrue(g["tolerance_needed"])
        self.assertIsNone(M.strict_goal([st]))                        # a tolerant pass alone is no strict goal
        self.assertEqual(task.config["minimum_coverage_ratio"], .95)  # restored after the replay
        self.assertNotIn("update", task.__dict__)

    def test_a_window_running_at_the_last_row_completes_in_the_hold(self):
        s, _ = scripted_session("blanket_flatten", lambda k: .96 if k >= 45 else .90)
        st = s.replay(ROWS, grading=True)
        g = st["grading"]
        self.assertTrue(st["success"])
        self.assertEqual(st["physics_steps"], 55)
        self.assertEqual((g["rows"], g["hold_steps"], g["success_in_hold"], g["strict_success"], g["tolerance_needed"]),
                         (5, 1, True, False, False))
        self.assertEqual(g["thresholds"]["coverage"]["window_ticks"], 11)
        self.assertTrue(g["thresholds"]["coverage"]["live_held"])
        plain, _ = scripted_session("blanket_flatten", lambda k: .96 if k >= 45 else .90)
        st = plain.replay(ROWS)                                       # not a grading replay: no hold, no record
        self.assertFalse(st["success"])
        self.assertNotIn("grading", st)
        self.assertEqual(st["sim_steps"], 5)

    def test_the_window_restarts_and_only_the_last_one_is_reported(self):
        cov = {**{k: .97 for k in range(10, 18)}, 18: .92, **{k: .94 for k in range(19, 200)}}
        s, _ = scripted_session("blanket_flatten", lambda k: cov.get(k, .90))
        g = s.replay(ROWS, grading=True)["grading"]
        self.assertTrue(g["success_in_hold"])
        self.assertEqual(g["thresholds"]["coverage"]["window_ticks"], 11)
        self.assertAlmostEqual(g["thresholds"]["coverage"]["window_worst"], .94)

    def test_no_success_holds_the_full_two_seconds_then_stops(self):
        s, _ = scripted_session("blanket_flatten", lambda k: .91)
        st = s.replay(ROWS, grading=True)
        g = st["grading"]
        self.assertFalse(st["success"])
        self.assertEqual((g["rows"], g["hold_steps"], g["hold_limit_steps"], g["strict_success"]), (5, 80, 80, False))
        self.assertEqual(st["sim_steps"], 85)
        self.assertNotIn("window_worst", g["thresholds"]["coverage"])
        self.assertFalse(g["tolerance_needed"])

    def test_a_failure_in_the_hold_ends_it_and_is_never_relaxed(self):
        s, _ = scripted_session("blanket_flatten", lambda k: .90, fell_at=63)
        st = s.replay(ROWS, grading=True)
        self.assertFalse(st["success"])
        self.assertEqual(st["episode_end"], "Cloth fell below the table")
        self.assertEqual((st["grading"]["hold_steps"], st["physics_steps"]), (2, 63))

    def test_an_episode_that_ended_within_the_rows_is_not_held(self):
        s, task = scripted_session("blanket_flatten", lambda k: .90, fell_at=12)
        st = s.replay(ROWS, grading=True)
        self.assertEqual((st["grading"]["rows"], st["grading"]["hold_steps"], st["physics_steps"]), (2, 0, 12))
        self.assertEqual(task.config["minimum_coverage_ratio"], .95)  # never relaxed

    def test_the_tick_ledger_of_a_partial_last_row_is_kept(self):
        s, _ = scripted_session("blanket_flatten", lambda k: .96 if k >= 44 else .90)
        st = s.replay(ROWS, physics_steps=[10, 10, 10, 10, 8], grading=True)
        self.assertTrue(st["success"])
        self.assertEqual((st["physics_steps"], st["grading"]["hold_steps"]), (54, 1))   # 48 ticks of rows, the hold to 54

    def test_cpu_families_and_unknown_families_replay_exactly_as_before(self):
        for fam in ("cast_coil", "interlocked_claws", "cube_pick_place"):
            a, _ = scripted_session(fam, lambda k: .96 if k >= 30 else .90)
            b, _ = scripted_session(fam, lambda k: .96 if k >= 30 else .90)
            st = a.replay(ROWS, grading=True)
            self.assertEqual(st, b.replay(ROWS))
            self.assertNotIn("grading", st)
            self.assertEqual(M.strict_goal([st]), (1, 4))              # a plain replay's success is strict

    def test_a_replay_that_raises_still_restores_the_task(self):
        s, task = scripted_session("blanket_flatten", lambda k: .90)
        own = s.step

        def broken(action, *, _physics_steps=None):
            if s.n_steps == 6:
                raise RuntimeError("simulator fault")
            return own(action, _physics_steps=_physics_steps)
        s.step = broken
        with self.assertRaises(RuntimeError):
            s.replay(ROWS, grading=True)                              # faults in the hold, thresholds relaxed
        self.assertEqual((task.config["minimum_coverage_ratio"], task.config["maximum_speed_m_s"]), (.95, .03))
        self.assertNotIn("update", task.__dict__)

    def test_the_hold_relaxes_the_speed_but_never_the_displacement(self):
        s, task = scripted_session("blanket_flatten", lambda k: .96, speed=lambda k: .05)
        st = s.replay(ROWS, grading=True)
        g = st["grading"]
        self.assertTrue(st["success"])                                # 0.05 m/s: settled only at the hold's 0.08 m/s
        self.assertEqual((g["strict_success"], g["success_in_hold"], g["tolerance_needed"]), (False, True, True))
        spd = g["thresholds"]["particle_speed"]
        self.assertEqual((spd["live"], spd["replay"], spd["live_held"]), (.03, .08, False))
        self.assertAlmostEqual(spd["window_worst"], .05)
        self.assertTrue(g["thresholds"]["coverage"]["live_held"])
        s, task = scripted_session("blanket_flatten", lambda k: .96, speed=lambda k: .05, drift=lambda k: .004)
        st = s.replay(ROWS, grading=True)                             # 4 mm of drift: the 3 mm limit is not relaxed
        self.assertFalse(st["success"])
        self.assertEqual(st["grading"]["hold_steps"], 80)
        s, task = scripted_session("blanket_flatten", lambda k: .96, speed=lambda k: .09)
        self.assertFalse(s.replay(ROWS, grading=True)["success"])     # faster than the hold's 0.08 m/s
        self.assertEqual((task.config["maximum_speed_m_s"], task.config["maximum_drift_m"]), (.03, .003))

    @unittest.skipUnless(importlib.util.find_spec("torch"), "the real blanket task needs the simulator image (torch)")
    def test_the_real_blanket_task_relaxes_only_its_speed_and_coverage(self):
        from topogym.tasks.blanket_flatten.blanket_flatten_medium import BlanketFlattenMediumTask
        task = BlanketFlattenMediumTask(dict(minimum_coverage_ratio=.95))
        seen = []
        s = object.__new__(M.Session)
        s.task, s.env, s.control_hz = "blanket_flatten", SimpleNamespace(_task=task), 40.
        s.episode_end, s.episode_done = None, False
        s.hold_action = lambda: None

        def step(action):
            spec = task.final_settling_spec()
            seen.append((task.config["minimum_coverage_ratio"], task.config["maximum_speed_m_s"], spec.maximum_speed_m_s,
                         task.config["maximum_drift_m"], spec.maximum_drift_m, task.config["stable_duration_s"]))
            s.episode_end = "success"                                 # one hold step is enough to look
        s.step = step
        policy = M._GradingReplay(s)
        policy.hold()
        policy.remove()
        self.assertEqual(seen, [(.92, .08, .08, .003, .003, .5)])     # the cheap gate and the settling speed, never the drift
        self.assertEqual((task.config["minimum_coverage_ratio"], task.config["maximum_speed_m_s"]), (.95, .03))
        self.assertEqual(task.final_settling_spec().maximum_speed_m_s, .03)


def module(name, relative):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


REVIEW = dict(pending=True, count=1, max_depth_mm=3.4, events=[dict(kind="deep", step=3, physics_step=27, ticks=2,
                                                                     bodies=["the claw 1", "the claw 0"], depth_mm=3.4, force_n=42.)])
FORCING = dict(count=1, longest_s=.6, events=[dict(arm="right", joint="waist", step=2, physics_step=17, ticks=240, fraction=1.,
                                                   cap_nm=12.9, max_force_n=102., pressing="the piece 1 it holds", on="the piece 0")])


def replay_status(success, strict=None, hold=0, row=4, review=None, forcing=None):
    """A Session.replay status: strict=None -> a plain replay (no grading record)."""
    st = dict(success=success, state_sha="s", sim_steps=row + hold, physics_steps=10 * (row + hold), sim_time_s=.25,
              progress=float(success), episode_end="success" if success else None, review=review, forcing=forcing)
    if strict is not None:
        st["grading"] = dict(revision=M.GRADING_REVISION, rows=row, strict_success=strict, success_row=row if strict else None,
                             hold_steps=hold, hold_limit_steps=80, success_in_hold=success and hold > 0,
                             thresholds={}, tolerance_needed=False)
    return st


class Graders(unittest.TestCase):
    def privileged(self, statuses):
        """The privileged tests/grade.py over scripted replay statuses (in order); returns (reward, verdict, kwargs)."""
        import json
        import tempfile
        from unittest.mock import patch
        grade = module("v16_grade", "harbor_templates/topogym/unlimited/tests/grade.py")
        calls = []

        class FakeSession:
            instance_matches = instance_exact = True
            runtime_binding = {"binding_id": "b"}

            def __init__(self, *a, **kw):
                self.queue = list(statuses)

            def replay(self, acts, **kw):
                calls.append(kw)
                return self.queue.pop(0)

            def start_video(self, *a, **kw):
                pass

            def stop_video(self):
                pass

            def render_review_frames(self, acts, events, out_dir, **kw):
                calls.append(dict(frames=[e["step"] for e in events]))
                return [os.path.join(out_dir, "step_00003.png")]

            def close(self):
                pass
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "instance.json").write_text('{"action_dim": 2, "action_layout": ["a", "b"]}')
            np.savez(root / "trajectory.npz", task="fixture", actions=np.zeros((4, 2)), action_layout=np.array(["a", "b"]))
            args = ["grade", "--family", "fixture", "--instance", str(root / "instance.json"), "--traj", str(root / "trajectory.npz"),
                    "--no-video"]
            with patch.object(grade, "LOG_DIR", d), patch.object(sys, "argv", args), patch.object(M, "Session", FakeSession), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(grade.main(), 0)
            return json.loads((root / "reward.json").read_text()), json.loads((root / "verdict.json").read_text()), calls

    def test_privileged_needs_a_strict_goal_in_one_replay(self):
        reward, verdict, calls = self.privileged([replay_status(True, strict=False, hold=3), replay_status(True, strict=True)])
        self.assertTrue(all(c.get("grading") for c in calls))        # both replays are grading replays
        self.assertEqual((reward["success"], reward["strict_goal_reached"], reward["strict_goal_row"]), (1, 1, 4))
        self.assertEqual(verdict["evidence"]["strict_goal"], {"replay": 2, "row": 4})
        self.assertEqual(reward["replay_hold_steps"], 3)

    def test_privileged_tolerant_passes_alone_fail(self):
        reward, verdict, _ = self.privileged([replay_status(True, strict=False, hold=3), replay_status(True, strict=False, hold=7)])
        self.assertEqual((reward["success"], reward["all_success"], reward["strict_goal_reached"], reward["strict_goal_row"]),
                         (0, 1, 0, 0))
        self.assertIsNone(verdict["evidence"]["strict_goal"])

    def test_privileged_a_failed_replay_still_fails(self):
        reward, _, _ = self.privileged([replay_status(True, strict=True), replay_status(False, strict=False, hold=80)])
        self.assertEqual((reward["success"], reward["all_success"], reward["strict_goal_reached"]), (0, 0, 1))

    def test_privileged_cpu_family_unchanged(self):
        reward, verdict, _ = self.privileged([replay_status(True), replay_status(True)])
        self.assertEqual((reward["success"], reward["strict_goal_reached"], reward["replay_hold_steps"]), (1, 1, 0))
        self.assertEqual((reward["success_pending_review"], reward["review_events"]), (0, 0))
        self.assertIsNone(verdict["evidence"]["review"])

    def test_privileged_a_success_with_a_deep_contact_is_held_for_review(self):
        reward, verdict, calls = self.privileged([replay_status(True), replay_status(True, review=REVIEW, forcing=FORCING)])
        self.assertEqual((reward["success"], reward["success_pending_review"], reward["all_success"]), (0, 1, 1))
        self.assertEqual((reward["review_events"], reward["review_max_depth_mm"], reward["forcing_events"]), (1, 3.4, 1))
        self.assertFalse(verdict["success"])
        self.assertEqual(verdict["evidence"]["review"]["replays"], [None, REVIEW])
        self.assertEqual(verdict["evidence"]["forcing"], [None, FORCING])
        self.assertEqual(verdict["evidence"]["review"]["frames"], ["review_frames/step_00003.png"])
        self.assertIn(dict(frames=[3, 2]), calls)                   # frames around the event and the forcing, one more replay

    def test_privileged_forcing_alone_is_evidence_and_the_success_is_credited(self):
        reward, verdict, calls = self.privileged([replay_status(True, forcing=FORCING), replay_status(True, forcing=FORCING)])
        self.assertEqual((reward["success"], reward["success_pending_review"], reward["forcing_events"]), (1, 0, 1))
        self.assertEqual(verdict["evidence"]["forcing"], [FORCING, FORCING])
        self.assertIsNone(verdict["evidence"]["review"])
        self.assertFalse(any("frames" in c for c in calls))

    def test_privileged_review_never_rescues_a_failure(self):
        reward, verdict, calls = self.privileged([replay_status(False, review=REVIEW), replay_status(True)])
        self.assertEqual((reward["success"], reward["success_pending_review"], reward["review_events"]), (0, 0, 1))
        self.assertFalse(any("frames" in c for c in calls))

    def standard(self, final):
        """The standard tests/grade.py over a final.json (paths rewritten as test-post-merge-repairs.py does)."""
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "final.json").write_text(json.dumps(final))
            np.savez(root / "trajectory.npz", task="fixture", actions=np.zeros((4, 2)), action_layout=np.array(["a", "b"]))
            source = (ROOT / "harbor_templates/topogym/limited/tests/grade.py").read_text()
            source = source.replace("/data/", d + "/").replace("/logs/verifier", str(root / "verifier"))
            source = source.replace("/tests/runtime_binding.json", str(root / "runtime_binding.json"))
            import hashlib
            expected = {"binding": "fixture"}
            (root / "runtime_binding.json").write_text(json.dumps(expected))
            wanted = hashlib.sha256(json.dumps(expected, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            for name in ("startup_binding.json", "replay.verdict.json"):
                (root / name).write_text(json.dumps({"instance_exact": True, "runtime_binding": {"binding_id": wanted}}))
            with contextlib.redirect_stdout(io.StringIO()):
                exec(compile(source, "standard_grade", "exec"), {})
            return json.loads((root / "verifier/reward.json").read_text())

    def test_standard_live_failure_is_final_whatever_the_replay(self):
        base = dict(finalized=True, deterministic=False, instance_matches=True, replay_hold_steps=12, replay_tolerance_needed=True)
        for reason in ("task_failed", "timeout"):
            reward = self.standard(dict(base, success=False, replay_success=True, reason=reason))
            self.assertEqual((reward["success"], reward["live_success"], reward["replay_success"]), (0, 0, 1))
        reward = self.standard(dict(base, success=True, replay_success=True, reason="success"))
        self.assertEqual((reward["success"], reward["replay_hold_steps"], reward["replay_tolerance_needed"]), (1, 12, 1))
        reward = self.standard(dict(base, success=True, replay_success=False, reason="success"))
        self.assertEqual(reward["success"], 0)

    def test_standard_a_success_with_a_deep_contact_is_held_for_review(self):
        base = dict(finalized=True, deterministic=True, instance_matches=True, success=True, replay_success=True, reason="success")
        reward = self.standard(dict(base, review=None, replay_review=None))
        self.assertEqual((reward["success"], reward["success_pending_review"], reward["review_events"]), (1, 0, 0))
        reward = self.standard(dict(base, forcing=FORCING, replay_forcing=FORCING))          # forcing alone: evidence only
        self.assertEqual((reward["success"], reward["success_pending_review"], reward["forcing_events"]), (1, 0, 1))
        for live, replay in ((REVIEW, None), (None, REVIEW), (REVIEW, REVIEW)):
            reward = self.standard(dict(base, review=live, replay_review=replay))
            self.assertEqual((reward["success"], reward["success_pending_review"], reward["review_max_depth_mm"]), (0, 1, 3.4))
        reward = self.standard(dict(base, success=False, review=REVIEW, reason="task_failed"))
        self.assertEqual((reward["success"], reward["success_pending_review"]), (0, 0))

    def test_standard_replay_is_tolerant_only_after_a_live_success(self):
        import json
        import runpy
        import tempfile
        from unittest.mock import patch
        for live, expected in ((True, True), (False, False)):
            calls = []

            class FakeSession:
                instance_sha, instance_exact, instance_matches = "s", True, True
                runtime_binding = {"binding_id": "b"}

                def __init__(self, *a, **kw):
                    pass

                def replay(self, acts, **kw):
                    calls.append(kw)
                    return dict(success=True, state_sha="s", sim_steps=4)

                def close(self):
                    pass
            with tempfile.TemporaryDirectory() as d:
                root = Path(d)
                (root / "instance.json").write_text('{"action_dim": 2, "action_layout": ["a", "b"]}')
                (root / "episode.json").write_text(json.dumps(dict(success=live, live_rows=4)))
                np.savez(root / "trajectory.npz", task="fixture", actions=np.zeros((4, 2)), action_layout=np.array(["a", "b"]))
                argv = ["replay", "--data", d, "--task", "fixture", "--instance", str(root / "instance.json")]
                with patch.object(M, "Session", FakeSession), patch.object(sys, "argv", argv), \
                        patch.dict(sys.modules, {"rcb_topogym": M}), contextlib.redirect_stdout(io.StringIO()):
                    try:
                        runpy.run_path(str(ROOT / "harbor_templates/topogym/limited/environment/sim/replay.py"), run_name="__main__")
                    except SystemExit:
                        pass
                verdict = json.loads((root / "replay.verdict.json").read_text())
            self.assertEqual(calls[0].get("grading"), expected)
            self.assertEqual(verdict["grading_replay"], expected)


class Texts(unittest.TestCase):
    def test_numbers_match_the_tooling(self):
        import topogym_rules as R
        self.assertEqual(R.REPLAY_TOLERANCES, M.REPLAY_TOLERANCES)
        self.assertEqual(R.GRADING_HOLD_S, M.GRADING_HOLD_S)
        self.assertEqual(set(R.TOLERANCE_WORDS), set(M._GRADING_VALUES))

    def test_blanket_words(self):
        import topogym_rules as R
        inst = {"effective_task_parameters": {"minimum_coverage_ratio": .95, "maximum_speed_m_s": .03}}
        for limited in (False, True):
            text = R.grading_replay_words("blanket_flatten", inst, limited=limited)
            self.assertIn("up to 2 s (80 control steps)", text)
            self.assertIn("a blanket coverage of 92% instead of 95%", text)
            self.assertIn("cloth speeds up to 80 mm/s instead of 30 mm/s (the displacement limit during the confirmation stays)",
                          text)
            self.assertIn("not bit-deterministic", text)
        details = R.grader_details("blanket_flatten", {**inst, "simulator": {}}, limited=True)
        self.assertTrue(any(line.startswith("Grading:") for line in details))
        self.assertFalse(any(line.startswith("Grading:") for line in R.grader_details("cast_coil", {"simulator": {}}, limited=True)))

    def test_the_hold_is_counted_at_the_instance_control_rate(self):
        """merged-v16 rope_threading runs one 40 ms tick per control step (25 Hz): 2 s are 50 control steps there, as the
        tooling counts them (GRADING_HOLD_S x Session.control_hz)."""
        import topogym_rules as R
        rope = {"effective_task_parameters": {"terminal": {"maximum_speed_m_s": .01}},
                "simulator": {"physics_dt_s": .04, "control_decimation": 1}}
        self.assertEqual(R.control_hz(rope), 25.)
        self.assertIn("up to 2 s (50 control steps)", R.grading_replay_words("rope_threading", rope, limited=True))
        self.assertIn("(no tolerance for this family)", R.grading_replay_words("rope_threading", rope, limited=False))
        self.assertEqual(R.control_hz({"simulator": {"physics_dt_s": .0025, "control_decimation": 10}}), 40.)


if __name__ == "__main__":
    unittest.main()
