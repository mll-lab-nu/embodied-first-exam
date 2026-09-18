"""Contact-gated runtime weld for the staged-lock key. No pose overwrites."""
import numpy as np
from scipy.spatial.transform import Rotation


def hand_pose(layout,depth,angle,roll_bias_deg=0.):
    r=Rotation.from_euler('x',-angle-roll_bias_deg,degrees=True)*Rotation.from_euler('y',90,degrees=True)
    q=r.as_quat()[[3,0,1,2]]
    return layout.grip_pos(depth)-r.apply([0,0,.1029]),q


def actual_hand_pose(task):
    """Grasp the measured free-body pose, including pitch/yaw on the rests."""
    state=task.state()
    key_r=Rotation.from_quat(np.asarray(state['key_quat'])[[1,2,3,0]])
    bias=float(task.cfg.motion.get('grasp_roll_bias_deg',0.))
    hand_r=key_r*Rotation.from_euler('x',-bias,degrees=True)*Rotation.from_euler('y',90,degrees=True)
    pad=np.asarray(state['key_tip_pos'])+key_r.apply([-task.layout.grip_offset,0,0])
    return pad-hand_r.apply([0,0,.1029]),hand_r.as_quat()[[3,0,1,2]]


class StagedLockGrasp:
    def __init__(self,task,controller):
        self.task,self.controller=task,controller
        self.active=False
        self.attach_error=None

    def attach(self):
        c=self.controller
        fingers={c.robot.get_link(name).idx for name in ('left_finger','right_finger')}
        # Check simultaneous bilateral contact. A sub-millimetre centering
        # error can leave one finger clear of the key resting in its cradle.
        # Recenter through ordinary joint control with a tighter IK tolerance;
        # never combine historical contacts or snap the key to the hand.
        for attempt in range(4):
            pad=c.grasp_center_pos()
            self.attach_error=float(np.linalg.norm(pad-self.task.actual_grip_pos()))
            if self.attach_error > float(self.task.cfg.assist.max_grasp_distance):
                raise RuntimeError(f'Grasp too far from key: {self.attach_error:.4f} m')
            if float(np.max(c.gripper_qpos())) > self.task.layout.handle_radius+.005:
                raise RuntimeError('Close fingers before attaching')
            contacts=c.robot.get_contacts(with_entity=self.task.key)
            touched=set(contacts['link_a'].detach().cpu().numpy().reshape(-1).tolist()) | set(contacts['link_b'].detach().cpu().numpy().reshape(-1).tolist())
            if fingers.issubset(touched):
                break
            if attempt<3:
                pos,quat=actual_hand_pose(self.task)
                target=c.robot.inverse_kinematics(link=c.ee_link,pos=pos,quat=quat,
                    init_qpos=c.robot.get_qpos(),dofs_idx_local=c.arm_dofs,
                    max_samples=1,max_solver_iters=200,pos_tol=1e-5,rot_tol=1e-4)
                c.robot.control_dofs_position(target[:c.arm_joint_count],c.arm_dofs)
                c.step(60)
        else:
            raise RuntimeError(f'Both fingers must contact key: touched={touched}, required={fingers}, q={c.gripper_qpos()}, gap={self.attach_error}')
        self.links=(c.ee_link.idx,self.task.key.get_link('key').idx)
        self.task.scene.sim.rigid_solver.add_weld_constraint(*self.links)
        self.active=True

    def detach(self):
        if self.active:
            self.task.scene.sim.rigid_solver.delete_weld_constraint(*self.links)
            self.active=False
