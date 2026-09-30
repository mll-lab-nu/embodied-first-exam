"""Effective public RoboCasa action contract; no simulator imports or hidden state."""
import copy
import math


def _json_limits(values):
    return [float(x) if math.isfinite(float(x)) else None for x in values]


def effective_spec(spec):
    """Keep upstream limits separately and describe every effective action channel."""
    out = copy.deepcopy(spec)
    dim = int(out['action_dim'])
    cfg = out['controller_configs']
    mink = cfg.get('type') == 'WHOLE_BODY_MINK_IK'
    out['native_advertised_limits'] = dict(lower=_json_limits(out['lower']), upper=_json_limits(out['upper']),
                                         unbounded_value=None)
    if mink:
        if dim != 24:
            raise ValueError('unsupported MINK layout; audit before generating')
        out['lower'] = [-10.] * 12 + [-3.] * 12
        out['upper'] = [10.] * 12 + [3.] * 12
        names = [f'{arm}_{axis}' for arm in ('right', 'left') for axis in ('x','y','z','rx','ry','rz')]
        names += [f'{arm}_{finger}' for arm in ('right','left') for finger in
                  ('little','ring','middle','index','thumb_flexion','thumb_rotation')]
        units = ['m','m','m','rad','rad','rad'] * 2 + ['unscaled_hand_command'] * 12
        out['action_frame'] = 'robot base; absolute XYZ and axis-angle; not world coordinates'
        out['hand_semantics'] = 'Unscaled Fourier commands, each in [-3,3]; use the six channels in listed order. Not binary grips.'
    else:
        if dim not in (12,13):
            raise ValueError('unsupported mobile Panda layout; audit before generating')
        out['lower'] = [float(v) for v in out['lower']]
        out['upper'] = [float(v) for v in out['upper']]
        if not all(math.isfinite(v) for v in out['lower'] + out['upper']):
            raise ValueError('nonfinite effective Panda bound')
        out['action_parts']['hybrid_mode'] = [dim-1,dim]
        if dim == 13:
            names = [f'arm_joint_{i+1}' for i in range(7)]
            units = ['rad'] * 7
            out['action_frame'] = 'absolute arm joint positions; base controls in robot base frame'
        else:
            names = ['arm_dx','arm_dy','arm_dz','arm_drx','arm_dry','arm_drz']
            units = ['normalised_translation'] * 3 + ['normalised_axis_angle'] * 3
            arm_cfg = cfg.get('body_parts',{}).get('right',cfg)
            out['action_frame'] = 'arm deltas in '+arm_cfg.get('input_ref_frame','base')+' frame; base controls in robot base frame'
            out['arm_output_scale'] = arm_cfg.get('output_max',[.05,.05,.05,.5,.5,.5])
        names += ['grip','base_x','base_y','base_yaw','torso','hybrid_mode']
        units += ['normalised_grip','normalised_velocity','normalised_velocity','normalised_yaw_velocity','normalised_torso','mode']
        out['hybrid_mode'] = dict(index=dim-1, lower=-1, upper=1, default=-1,
            positive='base mode; arm goal tracks the moving base using the desired goal',
            nonpositive='arm mode; arm goal updates from achieved pose')
        out['gripper_semantics'] = 'Positive closes, negative opens.'
    covered = [i for lo,hi in out['action_parts'].values() for i in range(lo,hi)]
    if sorted(covered) != list(range(dim)):
        raise ValueError('action parts must cover each dimension exactly once')
    out['channels'] = [dict(index=i,name=n,unit=u,lower=out['lower'][i],upper=out['upper'][i])
                       for i,(n,u) in enumerate(zip(names,units))]
    assert len(out['channels']) == dim
    out['schema'] = 'rcb-casa-effective-action-spec-v2'
    out['pose_convention'] = 'Observed body state: world metres / WXYZ. Actions: see action_frame and channels.'
    return out


def from_env(env):
    """Read controller structure only; called by privileged agent runtime."""
    robot = env.robots[0]
    parts = dict(getattr(robot.composite_controller,'_whole_body_controller_action_split_indexes',{}) or robot._action_split_indexes)
    cfg = getattr(robot,'composite_controller_config',None)
    # Use the controller's class and dimensions to identify the effective layout.
    if robot.robot_model.__class__.__name__ == 'GR1ArmsAndWaistFourierHands':
        cfg = dict(type='WHOLE_BODY_MINK_IK')
    else:
        cfg = dict(type='HYBRID_MOBILE_BASE')
    lo,hi = env.action_spec
    return effective_spec(dict(action_dim=env.action_dim,control_hz=env.control_freq,
                               action_parts=parts,lower=lo.tolist(),upper=hi.tolist(),controller_configs=cfg))
