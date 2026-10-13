import math
JOINT_NAMES = [f'{side}_{part}_joint' for side in ['left', 'right'] for part in ['hip_pitch', 'hip_roll', 'hip_yaw', 'knee', 'ankle_pitch', 'ankle_roll']] + [f'waist_{axis}_joint' for axis in ['yaw', 'roll', 'pitch']] + [f'{side}_{part}_joint' for side in ['left', 'right'] for part in ['shoulder_pitch', 'shoulder_roll', 'shoulder_yaw', 'elbow', 'wrist_roll', 'wrist_pitch', 'wrist_yaw']]
BOUNDS = {'learning_rate': (3e-05, 0.003), 'entropy_coef': (0.0, 0.03), 'friction_low': (0.1, 1.0), 'friction_high': (1.0, 2.0), 'encoder_bias': (0.0, 0.04), 'com_offset': (0.0, 0.08), 'action_rate_weight': (-0.2, 0.0)}
BASELINE = {'learning_rate': 0.001, 'entropy_coef': 0.01, 'friction_low': 0.3, 'friction_high': 1.6, 'encoder_bias': 0.015, 'com_offset': 0.05, 'action_rate_weight': -0.05}

def validate(c):
    if not isinstance(c, dict) or set(c) != set(BOUNDS):
        raise ValueError('Supply exactly the documented training settings')
    for k, (lo, hi) in BOUNDS.items():
        v = c[k]
        if type(v) not in (int, float) or not math.isfinite(v) or (not lo <= v <= hi):
            raise ValueError('Invalid setting: ' + k)
    if c['friction_low'] > c['friction_high']:
        raise ValueError('Invalid friction range')
    return dict(c)
