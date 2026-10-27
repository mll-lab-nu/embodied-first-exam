"""Scripted assembly policy: one grasp / insert / screw cycle per part of the plan.

The phase list is built at every reset from ``cfg["parts"]``::

    [Reach]* -> Grasp -> [Insert] -> [Screw]      (per part, in order)
    [Reach]                                        (optional final rehome)

``cfg["plan"]`` keys: ``rehome`` (fly back to the episode-start pose before every
part after the first), ``rehome_first`` (also before the first part),
``rehome_finish`` (after the last part). The per-skill parameter blocks
(``grasp`` / ``insert`` / ``screw``) at the task level are overridden by the
same-named blocks of each part entry.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core.policy import PhaseBase, PhasedPolicy
from .skills import GraspSkill, InsertSkill, ReachSkill, ScrewSkill

__all__ = ["RigidAssemblyPolicy"]


def _merge(base: Optional[Dict[str, Any]], over: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out = dict(base or {})
    out.update({k: v for k, v in (over or {}).items()})
    return out


class RigidAssemblyPolicy(PhasedPolicy):
    """Grasp -> insert -> (screw) over the parts of a :class:`~tactilelab_tasks.rigid.task.RigidAssemblyTask`."""

    def __init__(self, cfg: Dict[str, Any], task=None, verbose: bool = True, planner=None):
        super().__init__(phases=None, cfg=cfg, verbose=verbose)
        self.task = task
        self.planner = planner
        """Optional motion planner for the free-space legs (unused: the skills interpolate)."""

    def attach(self, task) -> "RigidAssemblyPolicy":
        self.task = task
        return self

    def build_phases(self, obs, info) -> List[PhaseBase]:
        if self.task is None:
            raise RuntimeError("RigidAssemblyPolicy needs the task (privileged object poses): policy.attach(task)")
        cfg = self.cfg
        plan = cfg.get("plan", {})
        seed = int(getattr(self.task, "seed", 0) or 0)
        phases: List[PhaseBase] = []
        for k, part in enumerate(cfg.get("parts", [])):
            if (k > 0 and plan.get("rehome", False)) or (k == 0 and plan.get("rehome_first", False)):
                phases.append(ReachSkill(self.task, cfg.get("reach", {}), part=k, verbose=self.verbose))
            phases.append(
                GraspSkill(
                    self.task,
                    _merge(cfg.get("grasp"), part.get("grasp")),
                    part=k,
                    skip_lift=bool(part.get("skip_lift", False)),
                    seed=seed,
                    verbose=self.verbose,
                )
            )
            if not part.get("skip_insert", False):
                phases.append(
                    InsertSkill(self.task, _merge(cfg.get("insert"), part.get("insert")), part=k, verbose=self.verbose)
                )
            if part.get("screw", False):
                phases.append(
                    ScrewSkill(
                        self.task, _merge(cfg.get("screw"), part.get("screw_params")), part=k, verbose=self.verbose
                    )
                )
        if plan.get("rehome_finish", False):
            phases.append(
                ReachSkill(self.task, cfg.get("reach", {}), part=len(cfg.get("parts", [])) - 1, verbose=self.verbose)
            )
        return phases

    @property
    def phase_names(self) -> List[str]:
        return [f"{p.name}_{getattr(p, 'part', 0)}" for p in self.phases]
