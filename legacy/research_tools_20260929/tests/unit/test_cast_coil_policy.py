"""Frozen route identity and feedback regression checks; no physics claims."""
import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from topogym.planning.cast_coil.policy import CastCoilPolicy, variant_reference


@pytest.mark.parametrize("variant,count", [("easy", 3), ("medium", 3), ("hard", 5)])
def test_registered_routes_are_continuous_and_reverse_to_assembly(variant, count):
    _, route = variant_reference(variant)
    assert len(route) == count
    np.testing.assert_allclose(route[0].pose(0)[0], np.eye(3), atol=1e-12)
    np.testing.assert_allclose(route[0].pose(0)[1], 0, atol=1e-12)
    for first, second in zip(route, route[1:]):
        for a, b in zip(first.pose(1), second.pose(0)):
            np.testing.assert_allclose(a, b, atol=1e-12)
    if variant == "medium":
        np.testing.assert_allclose(route[1].advance, [0, .009, 0])
    if variant == "hard":
        np.testing.assert_allclose(route[2].pose(1)[1]-route[2].pose(0)[1], [0, 0, .009])


def test_jammed_body_freezes_path_and_fails_instead_of_finishing():
    policy = CastCoilPolicy(body_origins={})
    policy.dt = .025
    policy.grip = .002
    clock = [0.]
    policy.time = lambda: clock[0]
    policy.tracking_error = lambda desired: (.008, .012)
    policy.attached_targets = lambda desired: desired
    queried = []
    def pose_at(u):
        queried.append(u)
        return {s: (np.zeros(3), Rotation.identity()) for s in ("left", "right")}
    program = policy.follow_bodies(pose_at, 3., "assembly_quarter_turn")
    with pytest.raises(RuntimeError, match="tracking stalled"):
        for _ in range(600):
            next(program)
            clock[0] += policy.dt
    assert max(queried) == 0


def test_jointly_displaced_parts_still_have_zero_relative_error():
    policy = CastCoilPolicy(body_origins={})
    desired = {"left": (np.array([.1, 0, 0]), Rotation.from_euler("y", -.4)),
               "right": (np.zeros(3), Rotation.identity())}
    turn = Rotation.from_euler("zyx", [.2, .5, -.1])
    policy.bodies = lambda: {s: (turn.apply(p)+[.3, .2, .1], turn*r) for s, (p,r) in desired.items()}
    absolute, relative = policy.tracking_error(desired)
    assert absolute > .1
    assert relative < 1e-15


@pytest.mark.parametrize("variant", ["medium", "hard"])
def test_grasp_tilt_cannot_put_the_assembled_placement_goal_below_table(variant):
    assembly, _ = variant_reference(variant)
    yaw = Rotation.from_euler("z", 90, degrees=True)
    level_origin = np.array([0., 0., .051])
    poses = {"right": (level_origin.copy(), yaw),
             "left": (np.array([.18, .12, .051]), yaw*Rotation.from_euler("y", -90, degrees=True))}
    placement = []

    class PlanningProbe(CastCoilPolicy):
        def bodies(self):
            return dict(poses)

        def tcp(self):
            return {s: (np.zeros(3), Rotation.identity()) for s in poses}

        def hold(self, seconds):
            if self.phase == "close_and_acquire":
                tilted = yaw*Rotation.from_euler("x", -1.2, degrees=True)
                # Gold still rests on an edge, but an assembled silver part
                # would intersect the table at this tilted support pose.
                height = -tilted.apply(assembly.bodies[0].visual.vertices)[:, 2].min()
                poses["right"] = (np.array([0., 0., height]), tilted)
            yield from ()

        def move(self, targets, seconds, phase):
            self.phase = phase
            yield from ()

        def follow_bodies(self, pose_at, seconds, phase):
            self.phase = phase
            goal = pose_at(1.)
            if phase == "place_assembly":
                placement.append(goal)
            poses.update(goal)
            yield from ()

    policy = PlanningProbe(body_origins={}, variant=variant)
    policy.initialize(dict(action_spec=dict(robot_id="aloha", mode="EE_ABS"),
                           timing_spec=dict(control_dt_s=.025)))
    policy.obs = dict(privileged=dict(world=dict(grasp=dict(hands={s: dict(phase="holding") for s in poses}))))
    list(policy.actions())
    assert len(placement) == 1
    for side, body in zip(("right", "left"), assembly.bodies):
        position, turn = placement[0][side]
        assert (turn.apply(body.visual.vertices)+position)[:, 2].min() >= -1e-12
        np.testing.assert_allclose(position, level_origin, atol=1e-12)
