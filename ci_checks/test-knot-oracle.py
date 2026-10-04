#!/usr/bin/env python3
"""Knot execution bookkeeping, upstream search, resume guards and safe CLI defaults (CPU only)."""
import copy
from pathlib import Path
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from topogym.planning.knot_untying.cli import normalize, parser
from topogym.planning.knot_untying.robot_oracle import Runner, Solved
from topogym.planning.knot_untying.branching import ARG_KEYS, CANDIDATES, Branching, SESSION_FIELDS, validate_candidate
from topogym.planning.knot_untying.artifacts import save_recording
from topogym.planning.knot_untying.replay_audit import assess, install_progress


def arguments(output, tier="hard", *extra):
    return normalize(parser(branching=True).parse_args(
        ["--variation", "knot_untying_"+tier, "--output", str(output), *extra]))


class KnotContracts(unittest.TestCase):
    def test_defaults_preserve_grasp_and_hard_full_withdrawal(self):
        for tier in ("easy", "medium", "hard"):
            a = arguments("/tmp/knot-unused", tier)
            self.assertEqual(a.close, .005)
            self.assertEqual(a.end_offset, .035)
            self.assertEqual(a.full_pull, tier == "hard")
            self.assertEqual(a.max_pull, .55 if tier == "hard" else .6)
            self.assertIsNone(a.max_nonprogress_decisions)
        self.assertFalse(arguments("/tmp/knot-unused", "hard", "--no-full-pull").full_pull)

    def test_default_input_matches_current_tooling_and_explicit_history_is_preserved(self):
        for tier in ("easy", "medium", "hard"):
            args = arguments("/tmp/knot-unused", tier)
            self.assertEqual(args.instance, ROOT / "tasks" /
                             f"topogym-knot-untying-{tier}-i00-privileged/environment/instance.json")
        historical = ROOT / "solvability_proof/knot_untying/2026-10-03_frozen_replay/evidence/instances/hard/instance.json"
        self.assertEqual(arguments("/tmp/knot-unused", "hard", "--instance", str(historical)).instance, historical)

    def test_invalid_commands_rejected_before_build(self):
        for key, value in (("close", "-0.001"), ("close", "nan"), ("speed", "nan"),
                           ("max-pull", "-1"), ("settle", "-1"), ("max-decisions", "0"),
                           ("max-nonprogress-decisions", "-1")):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                arguments("/tmp/knot-unused", "hard", "--"+key, value)
        for candidate in ({"close": -1}, {"full_pull": "false"}, {"unknown": 3},
                          {"direction": "x"}, {"lift": float("nan")}, {"straighten": 0}, []):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                validate_candidate(candidate)

    def test_terminal_step_uses_actual_tick_time_and_never_steps_twice(self):
        r = Runner.__new__(Runner)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        r.args = SimpleNamespace(output=Path(directory.name))
        r.validate_command = Mock()
        r.q, r.g, r.log = {}, {}, [dict(t=.025)]  # skip diagnostic sampling in this test
        s = SimpleNamespace(episode_end=None, episode_done=False, sim_time_s=.025, physics_steps=10,
                            hold_action=lambda: np.zeros(14))
        def step(row):
            s.sim_time_s += .0075; s.physics_steps += 3; s.episode_end = "success"
            return True
        s.step = Mock(side_effect=step)
        r.session = s
        r.task = SimpleNamespace(result=SimpleNamespace(metrics={"stable_time_s": .5}, reason=None, terminated=True, task_success=True))
        with self.assertRaises(Solved): r.step("settle")
        self.assertAlmostEqual(r.log[-1]["t"], .0325)
        self.assertEqual(r.log[-1]["physics_steps"], 13)
        with self.assertRaises(Solved): r.step("settle")
        self.assertEqual(s.step.call_count, 1)
        self.assertEqual(len(r.log), 2)

    def test_required_cartesian_path_cannot_silently_stop(self):
        r = Runner.__new__(Runner)
        r.q = {}; r.solve = Mock(side_effect=ValueError("unreachable")); r.step = Mock()
        with self.assertRaisesRegex(ValueError, "unreachable"):
            r.cartesian("left", [[0, 0, 0]], None, "carry")
        self.assertFalse(r.cartesian("left", [[0, 0, 0]], None, "pull", allow_partial=True))
        r.step.assert_not_called()

    def test_partial_recording_keeps_tick_ledger_and_recorder_running(self):
        with tempfile.TemporaryDirectory() as d:
            actions = [np.arange(14, dtype=np.float32)]
            s = SimpleNamespace(_recording=actions, _recorded_ticks=[3], action_dim=14,
                task="knot_untying", config=dict(task_id="knot_untying", variation_id="knot_untying_easy", seed=0),
                instance_sha="abc", action_layout=[str(x) for x in range(14)])
            p = Path(d)/"partial.npz"
            save_recording(s, p)
            with np.load(p, allow_pickle=False) as z:
                self.assertEqual(z["physics_steps_per_action"].tolist(), [3])
                np.testing.assert_array_equal(z["actions"], actions)
            self.assertIs(s._recording, actions)
            s._recorded_ticks = []
            with self.assertRaisesRegex(ValueError, "lengths differ"): save_recording(s, p)

    def test_restore_discards_rejected_actions_and_all_controller_future(self):
        b = Branching.__new__(Branching)
        s = SimpleNamespace(_recording=[1, 2, 3], _recorded_ticks=[10, 10, 10], _targets=np.ones(14))
        b.r = SimpleNamespace(session=s, env=SimpleNamespace(privileged=SimpleNamespace(rewind_to=Mock())))
        values = dict(n_steps=1, physics_steps=10, sim_time_s=.025, last_step_ticks=10,
                      _reward=0., episode_end=None, episode_done=False)
        mark = dict(ref={"state_id": 12}, runner=dict(log=[dict(t=.025)], decisions=[], q={"left": np.zeros(6)}),
                    selection=1, session=dict(**values, recording=1, ticks=1, targets=np.zeros(14)))
        b.selection = [dict(decision=1), dict(decision=2)]; b.backtracks = 0
        b.restore(mark)
        self.assertEqual(s._recording, [1]); self.assertEqual(s._recorded_ticks, [10])
        for key in SESSION_FIELDS: self.assertEqual(getattr(s, key), values[key])
        self.assertEqual(len(b.selection), 1); self.assertEqual(b.backtracks, 1)
        b.r.q["left"][0] = 7
        self.assertEqual(mark["runner"]["q"]["left"][0], 0)

    def test_resume_rejects_wrong_instance_or_incomplete_ticks_before_replay(self):
        b = Branching.__new__(Branching)
        s = SimpleNamespace(action_layout=["a"], action_dim=1, physics_substeps=10, step=Mock())
        b.r = SimpleNamespace(identity={"instance": "right"}, session=s)
        with self.assertRaisesRegex(ValueError, "identity"):
            b.resume(dict(schema_version=2, instance_identity={"instance": "wrong"}))
        with self.assertRaisesRegex(ValueError, "ledger"):
            b.resume(dict(schema_version=2, instance_identity=b.r.identity, action_layout=["a"],
                          actions=[[1.]], ticks=[]))
        s.step.assert_not_called()

    def test_downstream_failure_retries_parent_and_keeps_only_solved_prefix(self):
        with tempfile.TemporaryDirectory() as d:
            b = Branching.__new__(Branching)
            b.args = arguments(d); b.attempts = []; b.selection = []; b.start = 1; b.backtracks = 0
            r = SimpleNamespace(decisions=[], session=SimpleNamespace(sim_time_s=0.), count=4,
                                task=SimpleNamespace(result=SimpleNamespace(task_success=False)), prefix=[])
            r.crossings = lambda: [None]*r.count
            r.dump = Mock(); b.r = r; b.dump = Mock()
            def save_attempt_evidence(path):
                path.mkdir(parents=True, exist_ok=False)
                (path/"prefix.json").write_text(json.dumps(r.prefix))
            r.save_attempt_evidence = save_attempt_evidence
            b.kind = lambda _: "withdraw" if r.count == 4 else "straighten"
            def checkpoint(k):
                return copy.deepcopy((r.count, r.decisions, r.prefix, b.selection, r.session.sim_time_s))
            def restore(mark):
                r.count, r.decisions, r.prefix, b.selection, r.session.sim_time_s = copy.deepcopy(mark)
                b.backtracks += 1
            b.checkpoint, b.restore = checkpoint, restore
            b.candidates = lambda k, kind: iter([{"max_pull": .55}, {"max_pull": .65}] if k == 1 else [{}])
            b.choices = lambda k, crossings: ((b.kind(crossings), c) for c in b.candidates(k, b.kind(crossings)))
            def attempt(k, kind, candidate, before):
                r.session.sim_time_s += .025
                r.prefix.append((k, candidate))
                if k == 1:
                    r.count = 3 if candidate["max_pull"] == .55 else 1
                    return dict(kind=kind, crossings_before=4, crossings_after=r.count), None
                if r.count == 3:
                    return dict(kind=kind, crossings_after=1), "simulated downstream failure"
                r.task.result.task_success = True
                raise Solved()
            b.attempt = attempt
            self.assertTrue(b.run())
            self.assertEqual([x[1].get("max_pull") for x in r.prefix], [.65, None])
            self.assertEqual(len(b.selection), 2)
            self.assertEqual([x["result"] for x in b.attempts], ["rejected", "rejected", "solved_path", "solved_path"])
            self.assertEqual([x["attempt_id"] for x in b.attempts], [1, 2, 3, 4])
            self.assertEqual(b.backtracks, 2)
            evidence = Path(d)/"rejected_attempts"
            self.assertEqual(sorted(p.name for p in evidence.iterdir()), ["attempt_001", "attempt_002"])
            self.assertEqual(json.loads((evidence/"attempt_001/prefix.json").read_text()), [[1, {"max_pull": .55}]])
            self.assertEqual(json.loads((evidence/"attempt_002/prefix.json").read_text()),
                             [[1, {"max_pull": .55}], [2, {}]])

    def synthetic_search(self, output, outcomes):
        """A reversible primitive graph; executes the real search and heuristic handling."""
        b = Branching.__new__(Branching)
        b.args = arguments(output); b.attempts = []; b.selection = []; b.start = 1; b.backtracks = 0
        b.base_args = {key: getattr(b.args, key) for key in ARG_KEYS}; b.base_cfg = {}
        r = SimpleNamespace(decisions=[], session=SimpleNamespace(sim_time_s=0.), count=4,
                            task=SimpleNamespace(result=SimpleNamespace(task_success=False)), prefix=[], dump=Mock())
        r.crossings = lambda: [None]*r.count
        r.line = lambda: None
        def straighten(k, cfg):
            before = r.count
            result = outcomes[len(r.prefix)]
            r.session.sim_time_s += .025
            r.prefix.append(result)
            if result == "success":
                r.task.result.task_success = True
                raise Solved()
            if result == "invalid_volume":
                raise RuntimeError("episode ended: rope_volume_invalid")
            r.count = result
            return dict(kind="straighten", crossings_before=before, crossings_after=result)
        r.straighten = straighten
        b.r = r; b.dump = Mock(); b.tight_curl = lambda _: r.count == 1
        b.choices = lambda k, crossings: iter([("straighten", {})])
        b.checkpoint = lambda k: copy.deepcopy((r.count, r.decisions, r.prefix, b.selection, r.session.sim_time_s))
        def restore(mark):
            r.count, r.decisions, r.prefix, b.selection, r.session.sim_time_s = copy.deepcopy(mark)
            b.backtracks += 1
        b.restore = restore
        return b

    def test_same_or_increased_crossings_and_tight_curl_can_lead_to_success(self):
        for intermediate in (4, 5, 1):
            with self.subTest(intermediate=intermediate), tempfile.TemporaryDirectory() as d:
                b = self.synthetic_search(d, [intermediate, "success"])
                self.assertTrue(b.run())
                self.assertEqual(b.r.prefix, [intermediate, "success"])
                self.assertEqual(b.backtracks, 0)
                flag = "tight_curl_after_spread" if intermediate == 1 else "crossings_not_reduced"
                self.assertIn(flag, b.attempts[0]["heuristic_flags"])
                self.assertEqual([x["result"] for x in b.attempts], ["solved_path", "solved_path"])

    def test_crossing_oscillation_does_not_reset_nonprogress_budget(self):
        with tempfile.TemporaryDirectory() as d:
            b = self.synthetic_search(d, [5, 4, 5, "success"])
            b.args.max_nonprogress_decisions = 2
            self.assertFalse(b.run())
            self.assertEqual(len(b.attempts), 3)
            self.assertIn("nonprogress budget exhausted", b.attempts[-1]["reason"])
            self.assertEqual(b.attempts[-1]["best_crossings"], 4)
            self.assertEqual(b.r.prefix, [])
            # The same graph is reachable with a larger explicit exploration budget.
            b = self.synthetic_search(d, [5, 4, 5, "success"])
            b.args.max_nonprogress_decisions = 3
            self.assertTrue(b.run())

    def test_default_search_does_not_prune_a_long_nonprogress_prefix(self):
        with tempfile.TemporaryDirectory() as d:
            b = self.synthetic_search(d, [5, 4, 5, 4, 'success'])
            self.assertTrue(b.run())
            self.assertEqual(len(b.attempts), 5)

    def test_new_best_crossing_count_replenishes_nonprogress_budget(self):
        with tempfile.TemporaryDirectory() as d:
            b = self.synthetic_search(d, [5, 4, 3, 4, 3, "success"])
            self.assertTrue(b.run())
            self.assertEqual([x["nonprogress_decisions"] for x in b.attempts[:-1]], [1, 2, 0, 1, 2])

    def test_relaxed_search_still_rejects_native_physics_failure(self):
        with tempfile.TemporaryDirectory() as d:
            b = self.synthetic_search(d, ["invalid_volume", "success"])
            self.assertFalse(b.run())
            self.assertEqual(len(b.attempts), 1)
            self.assertIn("rope_volume_invalid", b.attempts[0]["reason"])
            self.assertEqual(b.r.prefix, [])

    def test_search_depth_and_total_attempt_budgets_remain_enforced(self):
        for key in ("max_decisions", "max_attempts"):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as d:
                b = self.synthetic_search(d, [3, 2, "success"])
                setattr(b.args, key, 1)
                self.assertFalse(b.run())
                self.assertEqual(len(b.attempts), 1)

    def test_both_primitive_families_precede_optional_operator_wait(self):
        b = Branching.__new__(Branching)
        b.kind = lambda _: "withdraw"
        b.base_cfg = {}; b.base_args = {}
        b.extra_candidates = Mock(return_value=iter([{"max_pull": .7}]))
        choices = b.choices(1, [1])
        self.assertEqual(next(choices), ("withdraw", {}))
        self.assertEqual(next(choices), ("straighten", {}))
        b.extra_candidates.assert_not_called()
        remaining = list(choices)
        self.assertEqual(remaining[-1], ("withdraw", {"max_pull": .7}))
        self.assertEqual(sum(kind == "straighten" for kind, _ in remaining), len(CANDIDATES['straighten'])-1)
        b.extra_candidates.assert_called_once_with(1, "withdraw")

    def test_zero_crossings_without_native_success_is_unsolved(self):
        with tempfile.TemporaryDirectory() as d:
            b = Branching.__new__(Branching); b.args = arguments(d)
            b.args.settle = .05; b.start = 1; b.dump = Mock(); b.attempts = []
            b.checkpoint = Mock(return_value={}); b.choices = Mock(return_value=iter([]))
            r = SimpleNamespace(decisions=[], session=SimpleNamespace(sim_time_s=0.), crossings=lambda: [],
                                dump=Mock(), task=SimpleNamespace(result=SimpleNamespace(task_success=False)))
            r.step = lambda phase: setattr(r.session, "sim_time_s", r.session.sim_time_s+.025)
            b.r = r
            self.assertFalse(b.run())
            b.choices.assert_called_once_with(1, [])
            self.assertGreaterEqual(r.session.sim_time_s, .05)

    def test_zero_crossing_repair_can_reach_native_success(self):
        with tempfile.TemporaryDirectory() as d:
            b = self.synthetic_search(d, ['success'])
            b.r.count = 0
            b.args.settle = .05
            b.r.step = lambda phase: setattr(b.r.session, 'sim_time_s', b.r.session.sim_time_s+.025)
            calls = []
            def arrange(k, cfg, mode):
                calls.append(mode)
                b.r.task.result.task_success = True
                raise Solved()
            b.r.arrange = arrange
            b.choices = lambda k, crossings: iter([('laydown', {})])
            self.assertTrue(b.run())
            self.assertEqual(calls, ['laydown'])

    def test_expanded_candidates_accept_native_valid_ranges(self):
        for rows in CANDIDATES.values():
            for candidate in rows:
                validate_candidate(candidate)
        validate_candidate(dict(lift=.2, straighten=1.1, close=0., span_ratio=None))
        for key in ('end_choice', 'arm_order', 'grasp_tilt_deg', 'grasp_yaw_deg', 'pull_pitch_deg', 'path_arch_m'):
            self.assertTrue(any(key in c for c in CANDIDATES['withdraw']), key)

    def test_audit_requires_actual_success_exact_instance_and_all_replays(self):
        report = dict(instance_matches=True, instance_exact=True, all_success=True, n_actions=5,
                      deterministic=False, replays=[dict(success=True, episode_end="success") for _ in range(2)])
        self.assertTrue(assess(report, repeat=2, exit_code=0, actions=5)["accepted"])
        for key, value in (("instance_exact", False), ("all_success", False), ("replays", report["replays"][:1]),
                           ("n_actions", 4), ("replays", [dict(success=True, episode_end="failed")]*2)):
            with self.subTest(key=key):
                self.assertFalse(assess(dict(report, **{key: value}), repeat=2, exit_code=0, actions=5)["accepted"])
        self.assertFalse(assess(report, repeat=2, exit_code=1, actions=5)["accepted"])
        single = assess(dict(report, replays=report["replays"][:1]), repeat=1, exit_code=0, actions=5)
        self.assertFalse(single["determinism_tested"])

    def test_replay_progress_preserves_native_calls_and_tick_requests(self):
        calls = []
        class Session:
            def __init__(self):
                self._resets = 0; self.n_steps = 0; self.physics_steps = 0; self.sim_time_s = 0.
                self.physics_substeps = 10
                self.episode_end = None
                self.env = SimpleNamespace(_task=SimpleNamespace(result=SimpleNamespace(
                    metrics={"stable_time_s": .4975, "quiet": True, "opaque": object()})))
            def step(self, action, *, _physics_steps):
                calls.append((action, _physics_steps))
                self.n_steps += 1; self.physics_steps += _physics_steps; self.sim_time_s += .0025*_physics_steps
                return False
            def replay(self, actions, *, physics_steps):
                self._resets += 1
                for action, ticks in zip(actions, physics_steps):
                    self.step(action, _physics_steps=ticks)
                return dict(success=False)
        with tempfile.TemporaryDirectory() as folder:
            install_progress(SimpleNamespace(Session=Session), folder)
            s = Session()
            self.assertEqual(s.replay([1, 2], physics_steps=[10, 3]), dict(success=False))
            self.assertEqual(calls, [(1, 10), (2, 3)])
            self.assertEqual(s.physics_steps, 13)
            self.assertTrue((Path(folder)/"replay_passes.jsonl").is_file())
            s.step(3, _physics_steps=2)
            progress = json.loads((Path(folder)/"replay_progress.json").read_text())
            self.assertEqual(progress["actions"], 3)
            self.assertEqual(progress["phase"], "step")
            self.assertEqual(progress["task_metrics"], {"stable_time_s": .4975, "quiet": True})
            self.assertEqual(calls, [(1, 10), (2, 3), (3, 2)])


if __name__ == "__main__":
    unittest.main()
