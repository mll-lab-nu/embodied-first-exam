"""Observation-only guards for diagnostic Hedgehog action sequences."""
import numpy as np

from topogym.planning.base import ActionSequencePolicy
from topogym.planning.rigid_reference.feedback import body_pose, relative_pose, errors


class ContactGuardedSequence(ActionSequencePolicy):
    """Stop the next control action on measured robot/fixture contact.

    The source is the tick-end Genesis contact sample. This cannot certify
    that no contact occurred between samples or within a solver substep.
    """
    def act(self, obs):
        world = obs["privileged"]["world"]
        bodies, contacts = world["bodies"], world["contacts"]
        robot = set(bodies["robot"]["link_indices"])
        fixtures = set().union(*(bodies[name]["link_indices"]
                                for name in ("hedgehog_cage", "hedgehog_mount")))
        table = set(bodies["table"]["link_indices"])
        base = min(robot)
        a = np.asarray(contacts["link_a"]).reshape(-1)
        b = np.asarray(contacts["link_b"]).reshape(-1)
        force = np.asarray(contacts["force"]).reshape(-1, 3)
        if not (len(a) == len(b) == len(force)) or not np.isfinite(force).all():
            raise RuntimeError("Missing or invalid contact sample")
        for x, y, f in zip(a, b, force):
            forbidden = ((x in robot and y in fixtures) or (y in robot and x in fixtures)
                         or (x in robot-{base} and y in table) or (y in robot-{base} and x in table))
            if forbidden and np.linalg.norm(f) > .01:
                raise RuntimeError(f"Forbidden robot/fixture contact: links {x}, {y}; force {np.linalg.norm(f):.6g} N")
        return super().act(obs)


class GraspGuardedSequence(ContactGuardedSequence):
    """Reject object/tool drift while following a measured rigid-grasp route."""
    def initialize(self, context):
        super().initialize(context)
        self.reference = None
        self.maximum_translation_m = self.maximum_rotation_rad = 0.

    def act(self, obs):
        world = obs["privileged"]["world"]
        hand = body_pose(world["articulations"]["robot"]["links"]["hand"])
        ball = body_pose(world["bodies"]["hedgehog_ball"])
        relative = relative_pose(hand, ball)
        if self.reference is None:
            self.reference = relative
        translation, angle = errors(relative, self.reference)
        self.maximum_translation_m = max(translation, self.maximum_translation_m)
        self.maximum_rotation_rad = max(angle, self.maximum_rotation_rad)
        if translation > .002 or angle > .05:
            raise RuntimeError(f"Grasp drift: {translation:.6g} m, {angle:.6g} rad")
        # This guard is used only after a verified lift clear of the support.
        # The planned rigid envelope has positive clearance to these fixtures.
        moving = set(world["bodies"]["hedgehog_ball"]["link_indices"])
        fixed = set().union(*(world["bodies"][name]["link_indices"]
                             for name in ("hedgehog_cage", "hedgehog_mount", "table")))
        contacts = world["contacts"]
        for a, b, f in zip(np.asarray(contacts["link_a"]).reshape(-1),
                           np.asarray(contacts["link_b"]).reshape(-1),
                           np.asarray(contacts["force"]).reshape(-1, 3)):
            if ((a in moving and b in fixed) or (b in moving and a in fixed)) and np.linalg.norm(f) > .05:
                raise RuntimeError("Held ball contacted a fixture during the clear transport phase")
        return super().act(obs)
