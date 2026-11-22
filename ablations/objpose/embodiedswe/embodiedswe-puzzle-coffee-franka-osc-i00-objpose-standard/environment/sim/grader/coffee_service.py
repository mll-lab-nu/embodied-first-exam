"""Grader for the coffee scene: one capsule coffee brewed and the filled mug set back on the tray.

Rubric stages (weights and modes live in RUBRIC) — the scene's own seven staged flags
(`CoffeeServiceScene.STAGES`), in the order the appliance's rules impose:
    pod_loaded   the capsule seated in the bay pocket (`pod_seated`)
    bay_closed   the cover slid shut over the seated capsule (`pod_seated & cover_closed`)
    cup_staged   the mug standing on the platform under the spout (`cup_under_spout`)
    started      the machine accepted START — it only does with cover closed, pod seated and
                 cup staged (the `started` event of the appliance state machine)
    brewed       the brew ran to completion: the machine's latched `filled` flag (an abort on
                 early open or on a spill never sets it)
    cup_out      the filled mug taken off the platform (`filled & ~cup_under_spout`)
    served       the filled mug resting upright, settled, on the tray dish — the scene's own
                 `success()`
The first six are milestones (a loaded pod, a closed bay or a staged cup need not persist once
the brew is done and the mug is carried away); the scene latches them itself at substep rate,
so the grader reads its flags. `brewed` is the machine's irreversible state, `served` is the
live end state. Success is the scene's `success()` on the final state.
"""

from __future__ import annotations

from robobench.core import BaseGrader
from robobench.suites.puzzle.scenes.coffee_service import CoffeeServiceScene


class CoffeeServiceGrader(BaseGrader):
    """The mug filled by a completed brew and resting upright, settled, on the serving tray.

    Ladder: pod loaded 0.143 · bay closed 0.286 · cup staged 0.429 · started 0.571 ·
            brewed 0.714 · cup out 0.857 · served 1.000
    (uniform: one unit per stage of the appliance's chain, the scene's own even credit).
    """

    SCENE = CoffeeServiceScene
    RUBRIC = (
        ("pod_loaded", 1, "once"),
        ("bay_closed", 1, "once"),
        ("cup_staged", 1, "once"),
        ("started", 1, "once"),
        ("brewed", 1),
        ("cup_out", 1, "once"),
        ("served", 1),
    )
    scene: CoffeeServiceScene

    def setup(self) -> None:
        # the flag columns, by the scene's own stage names
        self._col = {name: k for k, name in enumerate(self.scene.STAGES)}

    def check_success(self):
        return self.scene.success()  # filled AND on the tray, upright AND settled — live

    def _flag(self, name: str):
        return self.scene.stage_flags()[:, self._col[name]].float()

    # ---- rubric stages — each returns a (num_envs,) value in [0, 1] --------------------------
    def pod_loaded(self):
        return self._flag("pod_loaded")

    def bay_closed(self):
        return self._flag("bay_closed")

    def cup_staged(self):
        return self._flag("cup_staged")

    def started(self):
        return self._flag("started")

    def brewed(self):
        return self.scene.filled().float()

    def cup_out(self):
        return self._flag("cup_out")

    def served(self):
        return self.scene.success().float()
