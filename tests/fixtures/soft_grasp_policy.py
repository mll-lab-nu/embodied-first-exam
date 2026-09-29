"""Passive material pick/place policy; only public low-level action output."""
import numpy as np
from scipy.spatial.transform import Rotation, Slerp
from topogym.planning.examples.cube_pick_place import CubePickPlacePolicy


class SoftGraspPolicy(CubePickPlacePolicy):
    """Reuse pose interpolation, not a historical task's private physics loop."""
    def __init__(self, *, material='pbd', part='all', pickup_position_world_m=None, lift_height_m=.055):
        super().__init__(part=part, pickup_position_world_m=pickup_position_world_m)
        if not np.isfinite(lift_height_m) or lift_height_m <= .02:
            raise ValueError('Material fixture lift must be finite and greater than 20 mm')
        self.lift_height_m = float(lift_height_m)
        self.material = material
        self.material_index = None

    def initialize(self, context):
        self.robot_id = context['action_spec']['robot_id']
        if self.robot_id == 'panda_robotiq':
            super().initialize(context)
            self.downward = np.array([0.,1.,0.,0.])
        elif self.robot_id == 'aloha':
            if context['action_spec']['mode'] != 'EE_ABS' or context['mode'] != 'unlimited':
                raise ValueError('Material policy requires EE_ABS and authorized world observations')
            self.arm = 'left'
            group = context['action_spec']['groups'][self.arm]
            self.gripper_field = group['gripper_field']
            self.closed, self.opened = group['gripper_limits']
            self.dt = context['timing_spec']['control_dt_s']
            self._program, self.final_reason, self.phase = None, None, 'ready'
            # Local +X points down; the half-turn about it avoids an IK
            # solution on ALOHA's forearm-roll joint limit during contact.
            self.downward = np.array([0.,2**-.5,0.,-2**-.5])
        else:
            raise ValueError('Unsupported material fixture robot')
        self.material_index = None

    def _move(self, target, seconds, phase):
        # Same measured-pose interpolation as the current cube example, with
        # the tool-axis orientation selected for the fixture's real robot.
        self.phase = phase
        origin, start = self._position().copy(), self._time()
        q0 = np.asarray(self.obs['robot'][self.arm]['tcp_orientation_wxyz'])
        slerp = Slerp([0.,1.], Rotation.from_quat(np.array([q0,self.downward])[:,[1,2,3,0]]))
        while True:
            t = min(1., (self._time()-start+self.dt)/seconds)
            u = t*t*(3.-2.*t)
            yield {self.arm:dict(position_world_m=(origin+u*(target-origin)).tolist(),
                orientation_wxyz=slerp(u).as_quat()[[3,0,1,2]].tolist(), **{self.gripper_field:self.grip})}
            if t >= 1.-1e-9: break
        settled = self._time()
        while np.linalg.norm(self._position()-target) >= .003:
            if self._time()-settled >= .6-1e-9:
                raise RuntimeError('Material policy could not reach its stage target')
            yield {}

    def _cube_position(self):
        key = 'particles' if self.material == 'pbd' else 'fem'
        x = np.asarray(self.obs['privileged']['world'][key]['soft']['position_m'])
        if self.material_index is None:
            site = x[:, :2].mean(axis=0)
            if self.material == 'pbd':
                site[0] = x[:, 0].min()+.006  # Exposed boundary of this flat fixture.
            self.material_index = int(np.argmin(np.linalg.norm(x[:, :2]-site, axis=1)))
        return x[self.material_index].copy()

    def _actions(self):
        start = self._cube_position() if self.pickup_position is None else self.pickup_position.copy()
        self.pickup_position = start.copy()
        # Robotiq's pads travel downward then retract as its linkage closes.
        # Preshape above the table so that this arc does not sweep through a
        # thin sheet/rope. These are fixture policy targets, not backend gates.
        pinch = self.opened + (.8625 if self.material == 'pbd' else .825)*(self.closed-self.opened)
        if self.robot_id == 'aloha':
            pinch = self.closed+.004
        self.grip = self.opened if self.part != 'transfer' else pinch
        if self.part != 'transfer':
            self.phase = 'open'
            yield {self.arm: {self.gripper_field: self.opened}}
            yield from self._hold(.25)
            self.grip = pinch
            yield from self._move(start+[0, 0, .10], 1.5, 'approach')
            yield from self._hold(1.5)
            for action in self._move(start+[0, 0, .005], 1., 'descend'):
                yield action
                if self.obs['privileged']['world']['assist_active']:
                    break
            self.phase = 'close'
            yield {self.arm: {self.gripper_field: pinch}}
            if not self.obs['privileged']['world']['assist_active']:
                yield from self._hold(.5)
            # The parallel linkage's passive joints can keep changing the pad
            # height after the driver nearly settles. Follow the measured
            # material point with bounded ordinary pose actions until admission.
            for _ in range(20):
                if self.obs['privileged']['world']['assist_active']:
                    break
                site = self._cube_position()
                target = np.array([site[0], site[1], self._position()[2]-.002])
                for action in self._move(target, .15, 'contact_approach'):
                    yield action
                    if self.obs['privileged']['world']['assist_active']:
                        break
            if not self.obs['privileged']['world']['assist_active']:
                raise RuntimeError('Material policy did not acquire a qualified grasp')
            yield {self.arm:dict(position_world_m=self._position().tolist(),
                orientation_wxyz=self.downward.tolist(),
                **{self.gripper_field:pinch})}
            yield from self._move(start+[0, 0, self.lift_height_m], 1., 'lift')
            yield from self._hold(.25)
            if self._cube_position()[2] < start[2]+.02:
                raise RuntimeError('Material policy failed to lift actual material')
            if self.part == 'pickup':
                return
        yield from self._move(start+[.02, 0, self.lift_height_m], .8, 'carry')
        yield from self._move(start+[.02, 0, .007], .8, 'lower')
        self.phase, self.grip = 'release', self.opened
        yield {self.arm: {self.gripper_field: self.opened}}
        yield from self._hold(2.)
        if self.obs['privileged']['world']['assist_active']:
            raise RuntimeError('Material policy release left an active grasp')
        yield from self._move(start+[.02, 0, .12], 1., 'withdraw')
        yield from self._hold(.6)
