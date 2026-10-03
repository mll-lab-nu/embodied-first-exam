"""Opt-in reference capture around existing Keyhole generators, without changing actions."""
from copy import deepcopy

from topogym.planning.calibration_tools.contracts import digest
from topogym.planning.calibration_tools.tracking import pose_dict, relative
from topogym.planning.cast_keyhole.policy import ASSEMBLY_ROTATIONS, PARTS, CastKeyholePolicy
from topogym.planning.cast_keyhole.simplified_policy import SimplifiedKeyholePolicy


class ReferenceMixin:
    def act(self, observation):
        self._debug_reference = None
        return super().act(observation)

    def debug_reference(self):
        return deepcopy(getattr(self, "_debug_reference", None))

    def follow_bodies(self, pose_at, seconds, phase, **options):
        # The first pose_at call of each next(generator) is the target actually
        # used; precise-mode lookahead calls must not overwrite it.
        used = {}
        def annotated(progress):
            targets = pose_at(progress)
            if not used:
                turns = getattr(self, "assembly_rotations", ASSEMBLY_ROTATIONS)
                objects = {PARTS[s]: pose_dict(p+r.apply(self.origins[s]), r*turns[s].inv())
                           for s, (p, r) in targets.items()}
                used.update(progress_used=progress, objects=objects)
            return targets
        program = super().follow_bodies(annotated, seconds, phase, **options)
        plan_id = digest(dict(reference=self.reference, plan=self.plan, phase=phase, seconds=seconds))
        while True:
            used.clear()
            try:
                action = next(program)
            except StopIteration:
                return
            objects = used["objects"]
            self._debug_reference = dict(plan_id=plan_id, version=1, phase=phase,
                frame="world", units="m_wxyz", **deepcopy(used),
                relative_targets=[dict(entity=PARTS["right"], reference=PARTS["left"],
                    pose=relative(objects[PARTS["right"]], objects[PARTS["left"]]))])
            yield action


class ReferenceKeyholePolicy(ReferenceMixin, CastKeyholePolicy):
    pass


class ReferenceSimplifiedKeyholePolicy(ReferenceMixin, SimplifiedKeyholePolicy):
    pass


def make_policy(*, simplified=False, **kwargs):
    return (ReferenceSimplifiedKeyholePolicy if simplified else ReferenceKeyholePolicy)(**kwargs)
