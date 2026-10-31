"""insert_tube scripted demonstration policy.

Phases (right arm; the left arm holds its parked pose)::

    reach -> grasp (in place, gentle jaws) -> extract (out of the rack bore)
          -> insert (into the inclined slot) -> release, freeze

* ``grasp`` closes on the tube standing in the rack without the retrieval lift
  (the rack bore has sub-millimetre clearance; a free lift binds), with the
  episode-wide finger velocity / effort caps of ``cfg.grasp``;
* ``extract`` is the insert stroke reversed against the rack bore
  (``cfg.extract``: careful servo pull until the tip clears the entry, then one
  fast lift), finishing still held;
* ``insert`` runs the standard insert into the slot bore and releases once the
  tip is seated past the success depth; the hand freezes at the release pose and
  the task judges the opened jaws and the hand-to-tube distance.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ...core.policy import PhaseBase
from ...rigid.policy import RigidAssemblyPolicy
from ...rigid.skills import ExtractSkill, GraspSkill, InsertSkill, ReachSkill

__all__ = ["Policy"]

_EXTRACT_FROM_INSERT = (
    "press_allowance",
    "lateral_follow",
    "lateral_follow_alpha",
    "lateral_gain",
    "lateral_step_max",
    "lateral_deadband",
    "servo_track_thresh",
    "hold_decay",
)


class Policy(RigidAssemblyPolicy):
    """Reach -> grasp in place -> extract -> insert over the single part of cfg.yaml."""

    def build_phases(self, obs, info) -> List[PhaseBase]:
        if self.task is None:
            raise RuntimeError("Policy needs the task (privileged object poses): policy.attach(task)")
        cfg = self.cfg
        seed = int(getattr(self.task, "seed", 0) or 0)
        part = cfg["parts"][0]
        grasp = dict(cfg.get("grasp", {}))
        grasp.update(part.get("grasp", {}))
        insert = dict(cfg.get("insert", {}))
        insert.update(part.get("insert", {}))
        extract: Dict[str, Any] = {k: insert[k] for k in _EXTRACT_FROM_INSERT if k in insert}
        extract["max_steps"] = insert.get("insert_max_steps", 1500)
        extract.update(cfg.get("extract", {}))
        extract.pop("target", None)
        extract.pop("slot", None)
        return [
            ReachSkill(self.task, cfg.get("reach", {}), part=0, verbose=self.verbose),
            GraspSkill(self.task, grasp, part=0, skip_lift=True, seed=seed, verbose=self.verbose),
            ExtractSkill(self.task, extract, part=0, verbose=self.verbose),
            InsertSkill(self.task, insert, part=0, verbose=self.verbose),
        ]
