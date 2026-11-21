"""Grader for the stack_blocks scene: all blocks stacked into one upright tower on the pad.

Rubric stages (weights and modes live in RUBRIC):
    tower    contiguous tower height in blocks over cfg.n_blocks — the scene's own
             `tower_height()`: slots 0, 1, 2, ... above the pad centre, each filled by a block
             within cfg.align_tol of the pad axis, at the slot height within cfg.z_tol,
             upright within cfg.upright_max_deg, settled with the whole scene settled
             (cfg.settle_speed), counted up to the first empty slot
The cubes are identical sub-goals, so they share this ONE fraction stage (k/n_blocks). It is
LIVE: a toppled tower loses the credit. No grasp/lift rung: the scene defines no lift
threshold, so it is dropped rather than invented. Success is the scene's own `success()` —
every slot filled by exactly one block — read on the final state. With n_blocks blocks and
n_blocks slots, a full-height tower (every slot >= 1 block) is exactly one block per slot,
so the stage reaches 1 if and only if `success()` holds.
"""

from __future__ import annotations

from robobench.core import BaseGrader
from robobench.suites.puzzle.scenes.stack_blocks import StackBlocksScene


class StackBlocksGrader(BaseGrader):
    """One clean tower on the pad — every slot filled by exactly one upright, settled block.

    Ladder (k / n_blocks tower height; cfg.n_blocks = 4 by default): 1 block 0.25 ·
    2 blocks 0.50 · 3 blocks 0.75 · 4 blocks 1.00.
    """

    SCENE = StackBlocksScene
    RUBRIC = (("tower", 1),)
    scene: StackBlocksScene

    def setup(self) -> None:
        pass  # the pad axis is cfg.pad_pos (env-local) and the slots are cfg-derived; nothing to cache

    def check_success(self):
        return self.scene.success()  # (num_envs,) — every slot of that env holds exactly one block

    # ---- rubric stages — each returns a (num_envs,) value in [0, 1] -------------------------
    def tower(self):
        return self.scene.tower_height().float() / self.scene.cfg.n_blocks
