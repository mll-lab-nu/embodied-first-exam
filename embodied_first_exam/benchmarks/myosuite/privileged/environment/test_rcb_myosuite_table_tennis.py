"""Offline test of rcb_myosuite.Session.step's table_tennis end (no MyoSuite / MuJoCo needed).

MyoSuite 2.12.2's TableTennisEnvV0._get_done compares evaluate_pingpong_trajectory(...) (a ContactTrajIssue, a plain
enum.Enum) with the ints [0, 2, 3], so a lost rally never ends the episode upstream. Session.step ends it as a failure
at the step the rally is lost (and still ends a returned ball in success). The stub module below is MyoSuite 2.12.2's
own ContactTrajIssue, PingpongContactLabels and evaluate_pingpong_trajectory (myochallenge/tabletennis_v0.py),
verbatim; the fake env reproduces its `solved` (the check returns None) and its broken `done`.

  python3 embodied_first_exam/benchmarks/myosuite/privileged/environment/test_rcb_myosuite_table_tennis.py
"""
import enum
import os
import sys
import types
import unittest

import numpy as np

os.environ["RCB_SESSION_LOG"] = ""
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rcb_myosuite as M  # noqa: E402


class PingpongContactLabels(enum.Enum):
    PADDLE = 0
    OWN = 1
    OPPONENT = 2
    GROUND = 3
    NET = 4
    ENV = 5


class ContactTrajIssue(enum.Enum):
    OWN_HALF = 0
    MISS = 1
    NO_PADDLE = 2
    DOUBLE_TOUCH = 3


def evaluate_pingpong_trajectory(contact_trajectory):
    has_hit_paddle = False
    has_bounced_from_paddle = False
    has_bounced_from_table = False
    own_contact_count = 0
    own_contact_phase_done = False

    for s in contact_trajectory:
        if PingpongContactLabels.PADDLE not in s and has_hit_paddle:
            has_bounced_from_paddle = True
        if PingpongContactLabels.PADDLE in s and has_bounced_from_paddle:
            return ContactTrajIssue.DOUBLE_TOUCH
        if PingpongContactLabels.PADDLE in s:
            has_hit_paddle = True
        if PingpongContactLabels.OWN in s:
            if not has_bounced_from_table:
                has_bounced_from_table = True
                own_contact_count = 1
            elif not own_contact_phase_done:
                own_contact_count += 1
                if own_contact_count > 2:
                    own_contact_phase_done = True
                    return ContactTrajIssue.OWN_HALF
            else:
                return ContactTrajIssue.OWN_HALF
        elif has_bounced_from_table:
            own_contact_phase_done = True

        if PingpongContactLabels.OPPONENT in s:
            if has_hit_paddle:
                return None
            else:
                return ContactTrajIssue.NO_PADDLE

    return ContactTrajIssue.MISS


_mod = types.ModuleType("myosuite.envs.myo.myochallenge.tabletennis_v0")
_mod.ContactTrajIssue, _mod.PingpongContactLabels = ContactTrajIssue, PingpongContactLabels
_mod.evaluate_pingpong_trajectory = evaluate_pingpong_trajectory
for _name in ("myosuite", "myosuite.envs", "myosuite.envs.myo", "myosuite.envs.myo.myochallenge"):
    sys.modules.setdefault(_name, types.ModuleType(_name))
sys.modules[_mod.__name__] = _mod

P, OWN, OPP = PingpongContactLabels.PADDLE, PingpongContactLabels.OWN, PingpongContactLabels.OPPONENT
LIMIT = 300  # 3 s at 10 ms: upstream's MAX_TIME end


class FakeEnv:
    """Steps through a scripted ball-contact history; `solved` and `done` as MyoSuite 2.12.2 computes them."""

    def __init__(self, contacts):
        self.contacts, self.contact_trajectory, self.t = contacts, [], 0

    def step(self, a):
        self.contact_trajectory.append(self.contacts[self.t] if self.t < len(self.contacts) else set())
        self.t += 1
        solved = evaluate_pingpong_trajectory(self.contact_trajectory) is None
        done = self.t >= LIMIT or solved or evaluate_pingpong_trajectory(self.contact_trajectory) in [0, 2, 3]
        return None, 0.0, done, False, {"solved": np.array([[float(solved)]]), "done": np.array([[float(done)]])}


def session(contacts):
    s = M.Session.__new__(M.Session)
    s.task, s.rule, s.nu, s.max_steps, s.hold_steps = "table_tennis", "event", 2, M.MAX_STEPS, 1
    s.base, s._rec = FakeEnv(contacts), None
    s.steps, s.done, s.success, s.reason, s.solved_run, s.event_step, s.at_limit = 0, False, False, None, 0, None, False
    s.last_info = {}
    return s


def run(contacts, cap=LIMIT + 10):
    """Steps until the episode ends (or `cap` steps: an agent-ended episode runs on after its success event)."""
    s = session(contacts)
    while s.step(np.zeros(2)) and s.steps < cap:
        pass
    return s


def at(n, *pairs):
    c = [set() for _ in range(n)]
    for i, lab in pairs:
        c[i] = {lab}
    return c


SERVE = ((10, OWN), (11, OWN))                       # the serve's bounce: two control steps on the own half
RETURNED = at(60, *SERVE, (30, P), (50, OPP))        # paddle, then the opponent's half
SECOND_BOUNCE = at(60, *SERVE, (40, OWN))            # bounces twice on the own half
NO_PADDLE = at(60, *SERVE, (40, OPP))                # reaches the opponent's half untouched
DOUBLE_TOUCH = at(60, *SERVE, (30, P), (35, P))      # two paddle touches


class TableTennisEnd(unittest.TestCase):
    def check(self, agent_end):
        old = M.AGENT_END
        M.AGENT_END = agent_end
        try:
            s = run(RETURNED)
            self.assertTrue(s.success)
            self.assertEqual(s.event_step if agent_end else s.steps, 51)
            for contacts, lost_at in ((SECOND_BOUNCE, 41), (NO_PADDLE, 41), (DOUBLE_TOUCH, 36)):
                s = run(contacts)
                self.assertTrue(s.done)
                self.assertFalse(s.success)
                self.assertEqual(s.steps, lost_at, "the episode ends at the step the rally is lost, not at 3 s")
                self.assertTrue(s.reason.startswith("failure"))
        finally:
            M.AGENT_END = old

    def test_privileged(self):
        self.check(False)

    def test_agent_end(self):
        self.check(True)


if __name__ == "__main__":
    unittest.main()
