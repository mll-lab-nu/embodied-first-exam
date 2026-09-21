"""Native actuator motion and contact-gated grasp experiments for Orbits.

The runtime records physical joint/cord states. A trajectory is not a task
success certificate; pickup and solution qualification are separate checks.
"""
import json
import hashlib
from pathlib import Path

import mujoco
import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

from .robot_dynamics import build_robot_model
from .workspace import WorkspaceAudit
from .verification import threading_signature


class RobotRuntime:
    def __init__(self, cfg, folder, **model_kwargs):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=False)
        OmegaConf.save(cfg, self.folder/'config.yaml', resolve=True)
        self.model, self.data, self.initial, self.layout = build_robot_model(
            self.folder / 'model.xml', cfg, **model_kwargs)
        self.checker = WorkspaceAudit(cfg)
        self.checker.fixture = [part for part in self.checker.fixture
                                if part[0] not in ('cord', 'handle')]
        self.nodes = [self.model.site(f'node_{i}').id for i in range(len(self.initial))]
        self.actuated_q = self.model.jnt_qposadr[self.model.actuator_trnid[:, 0]]
        self.frames = []
        self.metrics = []
        self.events = []
        self.step_count = 0
        self.record('initial')

    def points(self):
        return self.data.site_xpos[self.nodes].copy()

    def record(self, phase):
        mujoco.mj_kinematics(self.model, self.data)
        self.frames.append((float(self.data.time), phase, self.data.qpos.copy(),
                            self.points(), self.data.ctrl.copy()))

    def joint_move(self, phase, target_q, seconds=2.):
        return self.joint_path(phase, np.asarray(target_q)[None, :], seconds)

    def joint_path(self, phase, waypoints, seconds=2., *, max_penetration_m=None):
        """Track a sampled joint path without jumping the physical state."""
        waypoints = np.asarray(waypoints, dtype=float)
        if (waypoints.ndim != 2 or waypoints.shape[1] < 16 or len(waypoints) == 0 or
                not np.isfinite(waypoints).all() or not np.isfinite(seconds) or seconds <= 0):
            raise ValueError('Joint path requires finite waypoints and positive duration')
        controls = np.vstack([self.data.ctrl, waypoints[:, self.actuated_q]])
        target = controls[-1]
        steps = round(seconds / self.model.opt.timestep)
        if steps < 1:
            raise ValueError('Joint path duration is shorter than one simulation step')
        if max_penetration_m is not None and (not np.isfinite(max_penetration_m) or max_penetration_m <= 0):
            raise ValueError('Contact guard requires a finite positive depth')
        depth = 0.
        pairs = set()
        for i in range(steps):
            u = (i + 1) / steps
            progress = u*u*(3-2*u)*(len(controls)-1)
            segment = min(int(progress), len(controls)-2)
            weight = progress-segment
            self.data.ctrl[:] = (1-weight)*controls[segment]+weight*controls[segment+1]
            mujoco.mj_step(self.model, self.data)
            self.step_count += 1
            if self.step_count % 10 == 0:
                for c in self.data.contact:
                    depth = max(depth, float(-c.dist))
                    names = [(self.model.body(self.model.geom_bodyid[int(g)]).name
                              or self.model.geom(int(g)).name) if g >= 0 else 'flex_cord'
                             for g in c.geom]
                    if c.dist < -.0002 and any('/' in n for n in names):
                        pairs.add(tuple(names))
                if max_penetration_m is not None and depth > max_penetration_m:
                    self.events.append(dict(event='contact_guard_stop', phase=phase,
                                            time_s=float(self.data.time), penetration_m=depth))
                    self.save()
                    raise RuntimeError(f'{phase}: contact penetration {depth:.6f} m exceeds guard')
            if self.step_count % 50 == 0:
                self.record(phase)
        metric = dict(phase=phase, time_s=float(self.data.time),
                      max_penetration_m=depth, robot_contact_pairs=sorted(pairs),
                      max_actuated_joint_error=float(np.max(np.abs(
                          self.data.qpos[self.actuated_q]-target))))
        self.metrics.append(metric)
        print(metric, flush=True)
        checkpoint = self.folder/'phase_checkpoints'/f'{len(self.metrics):03d}.npz'
        checkpoint.parent.mkdir(exist_ok=True)
        self.save_checkpoint(checkpoint)
        metric['checkpoint'] = str(checkpoint.relative_to(self.folder))
        self.save()

    def ik(self, side, point_local, rotation_world, seed=None):
        seed = self.data.qpos[:16].copy() if seed is None else seed.copy()
        point = self.checker.yaw.apply(point_local) + self.checker.origin
        q, pe, re = self.checker.solve(side, point, rotation_world, seed)
        if pe > .0005 or re > .005:
            raise ValueError(f'{side} IK failed: position={pe}, rotation={re}')
        # Preserve commanded squeezing force while changing the arm pose.
        q[[6, 7]] = self.data.ctrl[6]
        q[[14, 15]] = self.data.ctrl[13]
        return q, self.checker.violations(q)

    def grasp_contacts(self, side, target, *, node=None):
        """Opposing finger contacts at the requested material point.

        A contact with another part of the same cord cannot authorize a grasp.
        Flex element indices identify the two incident material vertices.
        """
        if node is not None and not 0 <= node < len(self.nodes):
            raise ValueError(f'Cord node out of range: {node}')
        cord_flex = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_FLEX, 'cord')
        fingers = set()
        for contact in self.data.contact:
            if contact.dist > 0 or contact.exclude:
                continue
            if node is not None:
                near_node = False
                for slot in range(2):
                    if int(contact.flex[slot]) != cord_flex:
                        continue
                    element = int(contact.elem[slot])
                    vertex = int(contact.vert[slot])
                    if vertex == node or (element >= 0 and node in (element, element+1)):
                        near_node = np.linalg.norm(contact.pos-self.points()[node]) <= .008
                if not near_node:
                    continue
            bodies = [self.model.body(self.model.geom_bodyid[int(g)]).name
                      if g >= 0 else 'cord' for g in contact.geom]
            if target in bodies:
                fingers.update(n for n in bodies if n.startswith(side+'/') and 'finger_link' in n)
        return sorted(fingers)

    def engage_grasp(self, side, *, node=None):
        if side not in ('left', 'right'):
            raise ValueError(f'Unknown arm: {side}')
        target = 'cord' if node is not None else 'handle'
        contacts = self.grasp_contacts(side, target, node=node)
        if len(contacts) != 2:
            raise ValueError(f'{side} cannot acquire {target}: bilateral contact missing')
        key = {('left', 'cord'): 'grasp_bight',
               ('right', 'cord'): 'grasp_fold_1',
               ('left', 'handle'): 'grasp_fold_0',
               ('right', 'handle'): 'grasp_handle'}[side, target]
        eid = self.model.equality(key).id
        self.release_grasp(side)
        self.model.eq_obj2id[eid] = (self.nodes[node] if node is not None
                                     else self.model.site('handle_center').id)
        grasp_site = int(self.model.eq_obj1id[eid])
        target_site = int(self.model.eq_obj2id[eid])
        body = int(self.model.site_bodyid[grasp_site])
        point = self.data.site_xpos[target_site].copy()
        rotation = self.data.xmat[body].reshape(3, 3)
        self.model.site_pos[grasp_site] = rotation.T @ (point-self.data.xpos[body])
        self.data.eq_active[eid] = True
        mujoco.mj_forward(self.model, self.data)
        self.events.append(dict(event='contact_gated_grasp_assist', time_s=float(self.data.time),
                                side=side, target=target, node=node, contacts=contacts,
                                world_point_task_m=point.tolist()))

    def release_grasp(self, side):
        """Release every assist on this arm before acquiring another object."""
        if side not in ('left', 'right'):
            raise ValueError(f'Unknown arm: {side}')
        names = ('grasp_bight', 'grasp_fold_0') if side == 'left' else ('grasp_handle', 'grasp_fold_1')
        released = []
        for name in names:
            eid = self.model.equality(name).id
            if self.data.eq_active[eid]:
                released.append(name)
                self.data.eq_active[eid] = False
        if released:
            self.events.append(dict(event='release_grasp_assist', time_s=float(self.data.time),
                                    side=side, equalities=released))

    def save_checkpoint(self, path):
        """Persist solver state and mutable grasp bindings for exact continuation."""
        spec = mujoco.mjtState.mjSTATE_INTEGRATION
        state = np.empty(mujoco.mj_stateSize(self.model, spec))
        mujoco.mj_getState(self.model, self.data, state, spec)
        np.savez_compressed(path, integration_state=state, state_spec=int(spec),
                            eq_obj2id=self.model.eq_obj2id,
                            site_pos=self.model.site_pos, step_count=self.step_count,
                            mujoco_version=mujoco.__version__,
                            model_xml_sha256=hashlib.sha256(
                                (self.folder/'model.xml').read_bytes()).hexdigest())

    def restore_checkpoint(self, path):
        """Resume a matching model; do not infer velocities from video frames."""
        with np.load(path) as saved:
            spec = int(saved['state_spec'])
            state = saved['integration_state']
            if (str(saved['mujoco_version']) != mujoco.__version__ or
                    str(saved['model_xml_sha256']) != hashlib.sha256(
                        (self.folder/'model.xml').read_bytes()).hexdigest() or
                    state.shape != (mujoco.mj_stateSize(self.model, spec),) or
                    saved['site_pos'].shape != self.model.site_pos.shape or
                    saved['eq_obj2id'].shape != self.model.eq_obj2id.shape):
                raise ValueError('Checkpoint does not match this robot model')
            self.model.eq_obj2id[:] = saved['eq_obj2id']
            self.model.site_pos[:] = saved['site_pos']
            mujoco.mj_setState(self.model, self.data, state, spec)
            self.step_count = int(saved['step_count'])
        mujoco.mj_forward(self.model, self.data)
        # Forward recomputes acceleration; preserve the saved warm start too.
        mujoco.mj_setState(self.model, self.data, state, spec)
        self.frames = []
        self.record('checkpoint_resume')
        self.events.append(dict(event='checkpoint_resume', source=str(path),
                                time_s=float(self.data.time)))

    def save(self):
        if self.frames[-1][0] != float(self.data.time):
            self.record('final')
        np.savez_compressed(self.folder/'trajectory.npz',
                            time_s=[f[0] for f in self.frames],
                            phase=[f[1] for f in self.frames],
                            qpos=[f[2] for f in self.frames],
                            points=[f[3] for f in self.frames],
                            ctrl=[f[4] for f in self.frames])
        self.save_checkpoint(self.folder/'checkpoint.npz')
        final_threading = threading_signature(self.points(), self.layout)
        (self.folder/'report.json').write_text(json.dumps(dict(
            scope='native_actuator_development_probe', full_task_success=False,
            final_time_s=float(self.data.time), final_threading=final_threading,
            metrics=self.metrics, events=self.events), indent=2)+'\n')
        scope_path = self.folder/'scope.json'
        if scope_path.exists():
            scope = json.loads(scope_path.read_text())
            scope.update(full_task_success=False, final_time_s=float(self.data.time),
                         final_threading=final_threading)
            scope_path.write_text(json.dumps(scope, indent=2)+'\n')


def pickup_probe(cfg, folder):
    runtime = RobotRuntime(cfg, folder)
    left_rotation = Rotation.from_euler('y', 30, degrees=True)
    right_rotation = Rotation.from_quat([.25881904510252074, 0, -.9659258262890683, 0])
    try:
        runtime.joint_move('settle', runtime.data.qpos.copy(), .5)
        for phase, side, point, rotation, seconds in [
            ('left_approach', 'left', [.111, .12, .08], left_rotation, 3.),
            ('left_lower_outside', 'left', [.111, .09, .025], left_rotation, 2.),
            ('left_bight_contact', 'left', [.111, 0, .025], left_rotation, 3.),
            ('right_approach', 'right', [.3225, -.10, .09], right_rotation, 3.),
            ('right_handle_contact', 'right', [.3225, 0, .012], right_rotation, 3.),
        ]:
            q, bad = runtime.ik(side, point, rotation)
            print(dict(phase=phase, ik_collisions=bad), flush=True)
            runtime.joint_move(phase, q, seconds)
        q = runtime.data.qpos[:16].copy()
        q[[6, 7, 14, 15]] = .002
        runtime.joint_move('close_fingers', q, 2.)
    finally:
        runtime.save()


if __name__ == '__main__':
    import argparse
    from hydra import compose, initialize_config_dir
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    args = parser.parse_args()
    with initialize_config_dir(config_dir=str(Path(__file__).resolve().parents[3]/'configs'), version_base='1.3'):
        cfg = compose(config_name='orbits_preview')
    pickup_probe(cfg, args.folder)
