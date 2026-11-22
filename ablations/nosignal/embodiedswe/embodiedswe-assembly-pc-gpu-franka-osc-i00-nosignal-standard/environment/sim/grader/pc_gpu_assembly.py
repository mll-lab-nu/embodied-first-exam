"""Grader for the pc_gpu scene: the graphics card seated in the PCIe x16 slot.

Rubric stages (weights and modes live in RUBRIC):
    grasped  the card has been taken in the weld-on-closure grip (`scene.grasp_held`) — the
             scene's own grasp state; a milestone, latched. Also true once the card is
             aligned in the slot (a card in the slot was necessarily carried there), so the
             rung nests under `aligned`. Under an embodiment with no gripper (the weld
             contract disabled, e.g. robot="null") the grasp state does not exist and the
             rung reads from that implication alone
    aligned  the card lined up on the slot — origin within `align_xy` of the seated point,
             up axis within `align_axis_deg` of the slot axis, length axis within
             `align_yaw_deg` of the slot heading: the scene's own three non-depth seat gates
    pressed  tab depth below the slot mouth (`slot_mouth_z`, the scene's own `engaged()`)
             as a fraction of `seat_depth`, counted only while aligned — so it is 1.0 iff
             the scene calls the card seated
Every stage is per env. The rungs nest (seated => aligned => grasped), so progress reaches
1.0 exactly when the card is seated, and for a grader built after the pick as well as one
that watched it. The rear-panel pass-through is NOT a rung: the cutout's geometry is not in
the scene cfg, so it cannot be read from state without an invented tolerance. Success is
the scene's `seated()` per env — depth, xy, tilt AND heading gates — read when the
delivery finishes.
"""

from __future__ import annotations

import math

from robobench.core import BaseGrader
from robobench.suites.assembly.scenes.pc_gpu_assembly import PcGpuAssemblyScene


class PcGpuAssemblyGrader(BaseGrader):
    """The card seated in its slot — pressed to depth, centred, upright, heading along the slot.

    Ladder: grasped 0.33 · aligned 0.67 · pressed 1.00 — three equal rungs for the three
    steps of the task (take the card, line it up on the slot, press it home); the last rung
    is a linear ramp of tab depth from the slot mouth (`slot_mouth_z`) to `seat_depth`.
    """

    SCENE = PcGpuAssemblyScene
    RUBRIC = (("grasped", 1, "once"), ("aligned", 1), ("pressed", 1))
    scene: PcGpuAssemblyScene

    def setup(self) -> None:
        import torch

        # `grasp_held` exists only while the weld contract is live (a gripper on the stage).
        self._has_grasp = hasattr(self.scene, "grasp_held")
        self._grasped = torch.zeros(self.num_envs, dtype=torch.bool,
                                    device=self.scene.engaged().device)  # latch: card ever held

    def check_success(self):
        return self.scene.seated()  # (num_envs,)

    def _aligned(self):
        """(num_envs,) bool: the scene's xy + tilt + heading seat gates, without depth."""
        c = self.scene.cfg
        rel = self.scene._card_offset_in_case()  # (n, 3), zero at the seated pose — privileged
        xy_ok = rel[:, :2].norm(dim=-1) <= c.align_xy
        up_ok = self.scene._axis_cos(2) >= math.cos(math.radians(c.align_axis_deg))
        yaw_ok = self.scene._axis_cos(0) >= math.cos(math.radians(c.align_yaw_deg))
        return xy_ok & up_ok & yaw_ok

    # ---- rubric stages — each returns a (num_envs,) value in [0, 1] ---------------------
    def grasped(self):
        if self._has_grasp:
            self._grasped |= self.scene.grasp_held.any(dim=1)
        return (self._grasped | self._aligned()).float()

    def aligned(self):
        return self._aligned().float()

    def pressed(self):
        depth = self.scene.engaged()  # (n,) tab depth below the slot mouth (m)
        return self._aligned() * (depth / self.scene.cfg.seat_depth).clamp(0.0, 1.0)
