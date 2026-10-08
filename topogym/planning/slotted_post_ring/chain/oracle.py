"""The oracle: the stages from a setting's reset in one Session, in turn; between them both hands go home, the scene
settles SETTLE_STEPS and the stage's end check (states.py) is noted in the log."""
from . import states
from .m1 import m1
from .m2 import m2
from .m3 import m3
from .m4a import m4a
from .m4b import m4b
from .session import scene

SETTLE_STEPS = 40
STAGES = (("M1", m1, states.s1), ("M2", m2, states.s2), ("M3", m3, states.s3), ("M4b", m4b, states.s4b),
          ("M4a", m4a, states.s4a))
GOAL_CHECKS = (states.s4a, states.s4b)    # the task's own goal check on the World state; the others take the scene


def run(H):
    session, task = H.session, H.session.env._task
    for name, run, check in STAGES:
        H.note("stage start", stage=name)
        run(H)
        for hand in ("A", "B"):
            H.go_home(hand)
        H.hold(SETTLE_STEPS)
        world = session.env.privileged.get("world")
        holds, measured = check(world, task) if check in GOAL_CHECKS else check(scene(session), task.layout)
        H.note("stage end", stage=name, holds=holds, checks=measured, episode_end=session.episode_end)
