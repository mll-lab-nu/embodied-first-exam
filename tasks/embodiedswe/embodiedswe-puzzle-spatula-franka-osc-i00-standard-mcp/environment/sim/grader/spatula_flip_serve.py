"""Grader for the spatula scene: the bread flipped in the pan and/or served onto the plate on the blade.

The scene's `cfg.goal` picks the chain (its own `_stage_table`); the rubric follows the goal,
uniform credit per rung:
    serve       lifted -> wedged -> loaded -> served
    flip        lifted -> wedged -> flipped_in_pan
    flip_serve  lifted -> wedged -> flipped -> loaded (after the flip) -> served

Rubric stages (weights and modes live in RUBRIC) — the scene's latched stages, read from its
substep-rate latches (the journey), plus the live destination:
    lifted           the blade above the surface by `lift_gate` (`_lifted`) — a milestone
    wedged           the bread riding the blade while still down at pan-floor level (`_wedged`)
    flipped          the bread inverted by >= `flip_min_deg` AND at rest flat in the pan
                     (`_flipped`); a milestone in `flip_serve` (the slice is served afterwards)
    loaded           the bread riding the blade above `lift_gate` — the friction carry
                     (`_loaded`; in `flip_serve` the scene's `_loaded_pf`, the carry AFTER the
                     flip, so a load during the flip lift earns nothing)
    served           the scene's `success()` for the serve goals: the bread resting flat on the
                     plate now, having ARRIVED ON THE BLADE (`_served`, the contact-history
                     clause; `flip_serve` also demands the flip latch)
    flipped_in_pan   the scene's `success()` for the flip goal: flipped latched AND the bread
                     resting inverted, flat and settled in the pan now
Success is the scene's own goal-dependent `success()` on the final state.
"""

from __future__ import annotations

from robobench.core import BaseGrader
from robobench.suites.puzzle.scenes.spatula_flip_serve import SpatulaFlipServeScene


class SpatulaFlipServeGrader(BaseGrader):
    """The bread flipped in the pan and/or served flat onto the plate (per the scene's goal), carried there on the blade.

    Ladder (uniform, one unit per rung of the goal's chain):
      flip_serve: lifted 0.20 · wedged 0.40 · flipped 0.60 · loaded after flip 0.80 · served 1.00
      serve:      lifted 0.25 · wedged 0.50 · loaded 0.75 · served 1.00
      flip:       lifted 0.333 · wedged 0.667 · flipped in pan 1.000
    """

    SCENE = SpatulaFlipServeScene
    RUBRICS = {
        "serve": (("lifted", 1, "once"), ("wedged", 1, "once"), ("loaded", 1, "once"),
                  ("served", 1)),
        "flip": (("lifted", 1, "once"), ("wedged", 1, "once"), ("flipped_in_pan", 1)),
        "flip_serve": (("lifted", 1, "once"), ("wedged", 1, "once"), ("flipped", 1, "once"),
                       ("loaded", 1, "once"), ("served", 1)),
    }
    RUBRIC = RUBRICS["flip_serve"]  # the scene's default goal
    scene: SpatulaFlipServeScene

    def __init__(self, env) -> None:
        # the chain is the scene's goal: pick that goal's rubric before the base wires the stages
        scene = getattr(env, "scene", None)
        if isinstance(scene, self.SCENE):
            self.RUBRIC = self.RUBRICS[scene.cfg.goal]
        super().__init__(env)

    def setup(self) -> None:
        self._goal = self.scene.cfg.goal

    def check_success(self):
        return self.scene.success()  # goal-dependent: the journey latches AND the live destination

    # ---- rubric stages — each returns a (num_envs,) value in [0, 1] --------------------------
    def lifted(self):
        return self.scene._lifted.float()

    def wedged(self):
        return self.scene._wedged.float()

    def flipped(self):
        return self.scene._flipped.float()

    def loaded(self):
        latch = self.scene._loaded_pf if self._goal == "flip_serve" else self.scene._loaded
        return latch.float()

    def served(self):
        return self.scene.success().float()

    def flipped_in_pan(self):
        return self.scene.success().float()
