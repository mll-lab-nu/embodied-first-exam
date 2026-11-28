"""Offline test of rcb_robowits.Session.replay at the step cap (no Genesis / torch needed: the physics is stubbed).

The instruction allows at most MAX_STEPS (200,000) rows; grade.py rejects only longer files. A trajectory of exactly
MAX_STEPS rows must be judged by the settle window (SETTLE_STEPS + CHECK_STEPS more steps) like any other, not raise
PrimitiveError (a grader_error), and one of MAX_STEPS - WINDOW .. MAX_STEPS - 1 rows (WINDOW = SETTLE_STEPS + CHECK_STEPS,
199,910 .. 199,999) must not fail on the step cap inside the settle window. A longer trajectory still meets the runaway
guard, and the cap holds again after the replay. The standard service's live window (sim/server.py settle(): the
episode's own journaling step, after /finish) runs the same way (Session.settle_past_cap): a live episode that ends in
that range is judged, not failed on the cap. The service itself builds a Genesis scene when imported, so the live case
runs the Session method it calls on the stub, and checks that settle() calls it.

  python3 embodied_first_exam/benchmarks/robowits/privileged/tests/test_rcb_robowits_step_cap.py
"""
import os
import sys
import unittest

import numpy as np

os.environ["RCB_SESSION_LOG"] = ""
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rcb_robowits as R  # noqa: E402


class _Env:
    def apply_action(self, a):
        pass


class _Th:
    @staticmethod
    def as_tensor(a, device=None):
        return a


class StubSession(R.Session):
    """A Session whose world is at rest with the goal holding; stepping only counts."""

    def __init__(self, max_steps=R.MAX_STEPS):          # noqa: D107 — no simulator
        self.task, self.max_steps = "dominos", int(max_steps)
        self.env, self.th, self.device = _Env(), _Th(), None
        self._recording, self._video, self._resets, self._total_steps = None, None, 0, 0
        self._targets = np.zeros(R.ACTION_DIM)
        self._restore()

    def _restore(self):
        self._recording, self.episode_done, self.n_steps = None, False, 0

    def goal(self):
        return {"success": True, "predicate": True, "clause": True, "touching": [], "objects": ["red block"]}

    def status(self):
        return {"success": True, "predicate": True, "touching": [], "progress": 1.0, "sim_steps": self.n_steps,
                "resets": self._resets, "state_sha": self.state_sha()}

    def state_sha(self):
        return str(self.n_steps)

    def object_pose(self, name):
        return np.zeros(3), np.array([1.0, 0, 0, 0])


WINDOW = R.SETTLE_STEPS + R.CHECK_STEPS


class StepCap(unittest.TestCase):
    def replay(self, rows, cap=R.MAX_STEPS):
        s = StubSession(cap)
        return s, s.replay(np.zeros((rows, R.ACTION_DIM), np.float32))

    def test_documented_maximum_is_graded(self):
        s, st = self.replay(R.MAX_STEPS)
        self.assertTrue(st["success"], st)
        self.assertEqual(st["sim_steps"], R.MAX_STEPS + WINDOW)
        self.assertTrue(s.episode_done)                          # the guard holds again after the replay
        self.assertEqual(s.max_steps, R.MAX_STEPS)
        with self.assertRaises(R.PrimitiveError):
            s.step(np.zeros(R.ACTION_DIM))

    def test_settle_window_not_cut_by_the_cap(self):
        for rows in (R.MAX_STEPS - WINDOW, R.MAX_STEPS - WINDOW + 1, R.MAX_STEPS - 1):
            s, st = self.replay(rows)
            self.assertTrue(st["success"], (rows, st["settle"]))
            self.assertEqual(st["settle"]["steps"], WINDOW)

    def live(self, steps):
        """A live episode `steps` control steps in (as the service's journaling step leaves it), and its journal."""
        s = StubSession()
        s.n_steps = steps                                   # the rows the agent's calls ran (stepping them changes nothing)
        journal = []

        def journal_step(a):                                # sim/server.py journal_step: executed, journaled, the guard
            guard = s.step(a); journal.append(a)
            return guard
        return s, journal, journal_step

    def test_live_window_at_the_lower_bound_needs_the_relaxation(self):
        s, _, step = self.live(R.MAX_STEPS - WINDOW)
        r = s.settle_check(step=step)                       # the window without settle_past_cap (the old live code)
        self.assertFalse(r["success"])
        self.assertTrue(r["why"].startswith("the step cap"), r)

    def test_live_window_not_cut_by_the_cap(self):
        for steps in (R.MAX_STEPS - WINDOW, R.MAX_STEPS - WINDOW + 1, R.MAX_STEPS - 1, 100):
            s, journal, step = self.live(steps)
            r = s.settle_past_cap(step=step)
            self.assertTrue(r["success"], (steps, r))
            self.assertEqual((r["steps"], len(journal), s.n_steps), (WINDOW, WINDOW, steps + WINDOW))
            self.assertEqual(s.max_steps, R.MAX_STEPS)          # the cap holds again after the window
            self.assertEqual(s.episode_done, s.n_steps >= R.MAX_STEPS)

    def test_live_service_runs_its_window_past_the_cap(self):
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "sim", "server.py")).read()
        body = src.split("\ndef settle(", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("S.settle_past_cap(step=step)", body)
        self.assertNotIn("S.settle_check(", body)

    def test_short_trajectory_unchanged(self):
        s, st = self.replay(100)
        self.assertTrue(st["success"])
        self.assertEqual(st["sim_steps"], 100 + WINDOW)
        self.assertFalse(s.episode_done)

    def test_longer_than_cap_still_meets_the_guard(self):
        with self.assertRaises(R.PrimitiveError):
            self.replay(1001, cap=1000)


if __name__ == "__main__":
    unittest.main()
