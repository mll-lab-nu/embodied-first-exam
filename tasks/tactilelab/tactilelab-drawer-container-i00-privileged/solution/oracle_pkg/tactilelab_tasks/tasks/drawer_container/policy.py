"""drawer_container scripted demonstration policy.

Per part of ``cfg.parts`` (bottom container, then top container)::

    reach (home) -> grasp (side wall, lift) -> insert (horizontal slide along the
    rail axis, released at the clearance stop) -> push (to the back stop)

The containers are grasped top-down by a side wall with the jaws closed to the
gel faces, slid nose-first into their rail pair until the wrist (or the fingertips)
would reach the box face (``eef_stop_axial`` / ``fingertip_stop_axial``, or the
per-part ``insert_stop_depth``) and released there; the hand lifts clear. Each part
entry with ``push: true`` then runs the staged push (``cfg.push`` plus the part's
``push_target`` / ``stage_floor``): the open fingers straddle the handle and press
the front wall until the container stops moving for ``stall_ticks``. Pushing the
bottom container home before the top one is inserted keeps the two strokes
independent (a single fist on both front walls stops when the top reaches its
back stop, leaving the bottom short of its gate).
"""

from __future__ import annotations

from typing import Any, Dict, List

from ...core.policy import PhaseBase
from ...rigid.policy import RigidAssemblyPolicy
from ...rigid.skills import GraspSkill, InsertSkill, PushSkill, ReachSkill

__all__ = ["Policy"]

_PART_PUSH_KEYS = ("push_target", "stage_floor", "axis", "stages", "joint_approach")


def _merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base or {})
    out.update(over or {})
    return out


class Policy(RigidAssemblyPolicy):
    """Reach -> grasp -> horizontal insert -> optional staged push, per container."""

    def build_phases(self, obs, info) -> List[PhaseBase]:
        if self.task is None:
            raise RuntimeError("Policy needs the task (privileged object poses): policy.attach(task)")
        cfg = self.cfg
        plan = cfg.get("plan", {})
        seed = int(getattr(self.task, "seed", 0) or 0)
        parts = cfg.get("parts", [])
        phases: List[PhaseBase] = []
        for k, part in enumerate(parts):
            if (k > 0 and plan.get("rehome", False)) or (k == 0 and plan.get("rehome_first", False)):
                phases.append(ReachSkill(self.task, cfg.get("reach", {}), part=k, verbose=self.verbose))
            phases.append(
                GraspSkill(
                    self.task,
                    _merge(cfg.get("grasp", {}), part.get("grasp", {})),
                    part=k,
                    skip_lift=bool(part.get("skip_lift", False)),
                    seed=seed,
                    verbose=self.verbose,
                )
            )
            if not part.get("skip_insert", False):
                insert = _merge(cfg.get("insert", {}), part.get("insert", {}))
                stop = insert.get("insert_stop_depth")
                if isinstance(stop, (list, tuple)):  # per-part stop depths
                    insert["insert_stop_depth"] = float(stop[min(k, len(stop) - 1)])
                phases.append(InsertSkill(self.task, insert, part=k, verbose=self.verbose))
            if part.get("push", False):
                push = _merge(cfg.get("push", {}), {key: part[key] for key in _PART_PUSH_KEYS if key in part})
                phases.append(PushSkill(self.task, push, part=k, verbose=self.verbose))
        if plan.get("rehome_finish", False):
            phases.append(ReachSkill(self.task, cfg.get("reach", {}), part=len(parts) - 1, verbose=self.verbose))
        return phases
