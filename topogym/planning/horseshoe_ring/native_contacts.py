"""Optional read-only robot contact screening under the native task limits.

This does not change collision response, assist acquisition, or acceptance.
An ordinary-action execution and its independent audit remain necessary.
"""
import fcl
import numpy as np

from topogym.utils.grasp import held_finger_contact_mask
from topogym.utils.snapshots import thaw
from .kinematics import HorseshoeIK


class ContactHorseshoeIK(HorseshoeIK):
    """Retain structural robot checks and classify all robot/puzzle contacts."""

    def __init__(self, env, *, puzzle_clearance_m=.0001, ordinary_limit_m=.0008):
        super().__init__(env, puzzle_clearance_m=puzzle_clearance_m)
        policy = env._task.terminal_metadata()['contact_penetration']
        self.ordinary_limit_m = float(ordinary_limit_m)
        if not 0 < self.ordinary_limit_m <= float(policy['other_contacts_m']):
            raise ValueError('Planning contact allowance exceeds the native ordinary limit')
        self.held_limit_m = float(policy['held_finger_contacts_m'])
        self.finger_ids = {
            side: [self.robot.entity.get_link(name).idx for name in group.grasp.finger_links]
            for side, group in self.robot.groups.items()
        }
        self.body_ids = {
            name: env._world.entities[name].links[0].idx for name in self.bodies
        }
        self.robot_link_ids = {
            name: self.robot.entity.get_link(name).idx for _, name, *_ in self.shapes
        }
        self.observed_grasp = None

    def observe_contacts(self, observation):
        self.observed_grasp = thaw(observation['privileged']['world'].get('grasp'))

    def check(self, q, *, contacts=None, body_poses=None):
        # The caller's contact hint cannot bypass the native classification.
        # Superclass checks still cover limits, self contact, the other arm,
        # and the table; only robot/puzzle distance checks are replaced below.
        checked = super().check(q, body_poses=body_poses, contacts={
            side: tuple(self.bodies) for side in self.robot.groups
        })
        task_issues = {
            side + '/' + body for side in self.robot.groups for body in self.bodies
        }
        issues = [issue for issue in checked['issues'] if issue not in task_issues]
        link_a, link_b, depths, pairs = [], [], [], []
        for _, link, _, _, shape in self.shapes:
            for body, (_, obstacle) in self.bodies.items():
                data = fcl.CollisionData(request=fcl.CollisionRequest(
                    num_max_contacts=256, enable_contact=True))
                obstacle.collide(shape, data, fcl.defaultCollisionCallback)
                for contact in data.result.contacts:
                    depth = float(contact.penetration_depth)
                    if depth < 0:
                        continue
                    link_a.append(self.robot_link_ids[link])
                    link_b.append(self.body_ids[body])
                    depths.append(depth)
                    pairs.append([link, body])
        record = dict(link_a=link_a, link_b=link_b, penetration=depths)
        held = held_finger_contact_mask(
            record, self.finger_ids, set(self.body_ids.values()), self.observed_grasp)
        depth = np.asarray(depths)
        limits = np.where(held, self.held_limit_m, self.ordinary_limit_m)
        violations = [
            dict(pair=pairs[i], depth_m=float(depth[i]), limit_m=float(limits[i]))
            for i in np.flatnonzero(depth > limits)
        ]
        if violations:
            issues.append('robot_task_contact_depth')
        return dict(checked, passed=not issues, issues=issues,
                    contact_violations=violations,
                    ordinary_depth_m=float(depth[~held].max(initial=0.)),
                    held_finger_depth_m=float(depth[held].max(initial=0.)),
                    contact_policy=dict(ordinary_m=self.ordinary_limit_m,
                                        qualified_fingers_m=self.held_limit_m),
                    scope='sampled FCL contacts; native physical contacts require execution')
