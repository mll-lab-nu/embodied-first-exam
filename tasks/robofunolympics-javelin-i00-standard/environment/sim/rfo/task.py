"""What a RoboFunOlympics family is: a venue, a start, and a referee (rfo/referee.py's toolkit). One module per family,
`rfo_task.py` in a task directory, defines `Task(TaskBase)`.

The referee's verdict is `success` = every stage latched in order under the task's conditions, with no rule violated;
a violation ends the episode as a failure at once, the time limit too."""
from __future__ import annotations


class TaskBase:
    name = ""                       # the family: robofunolympics-<name>-i00-<mode>
    title = ""
    category = ""                   # track-and-jumps | football-and-volleyball | basketball-and-rackets |
                                    # throwing-catching-striking | parkour-apparatus-balance
    robot = "unitree_g1"            # "unitree_g1" (1.32 m, 33 kg; walking and running policies) or "unitree_h1"
                                    # (the H1-2: 1.78 m, 67 kg; a walking policy): the size the official venue needs
    rulebook = ""                   # the rule book the family follows: name, edition, the articles used
    deviations: list[str] = []      # each departure from it: "<article>: what is different, and why" (never "easier")
    time_limit_s = 30.0             # the episode ends here as a failure ("time")
    start = (0.0, 0.0, 0.0)         # the robot's x, y (m) and yaw (rad) at t = 0
    stages: list[str] = []          # the events that must happen, in order
    fall_rule = True                # a fall fails the episode: the pelvis below fall_z, or a part of the robot that
    fall_z = 0.35                   # is not in legal_ground touching the ground
    legal_ground = ("left_foot", "right_foot")
    params: dict = {}               # the numbers of the rules (the instruction quotes them; an instance may override)

    def __init__(self):
        self.p = dict(self.params)
        self.trackers: dict = {}

    def configure(self, params: dict) -> None:
        unknown = set(params) - set(self.p)
        if unknown:
            raise KeyError(f"{self.name}: unknown parameter(s) {sorted(unknown)}")
        self.p.update(params)

    # ------------------------------------------------------------------ the venue and the start
    def build(self, sc) -> None:
        """Add the venue to the scene (rfo.scene.Scene)."""

    def reset(self, w) -> None:
        """Place the props (w.put / w.pin / w.grab) for t = 0. The robot already stands at `start`."""

    def referee_reset(self, w, ref) -> None:
        """Create the trackers (in self.trackers, so that they are part of the state hash)."""
        self.trackers = {}

    # ------------------------------------------------------------------ the referee's hooks
    def before_step(self, w) -> None:
        """At the start of every control step, before the action (launch a ball, move a target)."""

    def substep(self, w, ref) -> None:
        """After every physics step (1 ms): contact events, crossings."""

    def step(self, w, ref) -> None:
        """After every control step (10 ms): slower conditions, the final success."""

    def timeout(self, w, ref) -> None:
        """At the time limit, before the episode fails with "time" (a task judged at the end succeeds here)."""

    def may_grip(self, w, side: str, name: str) -> bool:
        """May this hand grip this object now (the task's own rule: no carrying in a bumping task, ...)."""
        return True

    # ------------------------------------------------------------------ the record
    def digest(self) -> list:
        """The trackers for the state hash: plain values, and objects (also inside lists and dicts) by their state()."""
        return [[k, v] for k, v in sorted(self.trackers.items())]

    def privileged(self, w) -> dict:
        """Task state for privileged mode's tooling (object poses, the referee's geometry)."""
        return {}

    # ------------------------------------------------------------------ texts (scripts/robofunolympics/gen_tasks.py)
    sentence = ""                   # one sentence: what to do
    rules = ""                      # the rule book, with {param} placeholders: every number the referee uses
    venue = ""                      # where things are at t = 0 in the robot's starting frame (privileged: exact;
                                    # standard: the rule-book layout, nothing an instance randomises)
    difficulty = ""
