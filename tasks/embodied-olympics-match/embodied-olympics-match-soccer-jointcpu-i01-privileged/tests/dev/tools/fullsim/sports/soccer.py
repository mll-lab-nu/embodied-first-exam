"""Humanoid robot soccer 2 v 2 at the joint level, the CPU resource tier: the privileged twin of
embodied-olympics-match-soccer-jointcpu-i01-realtime (coach format, level 5 = the learned joint-level team, seed 101, S = 10, 14400 s).

The twin's rules, referee, opponent, joint-level action layer and S = 10 clock are unchanged; the twin's observation
already holds the ball's and every robot's truth (RCB_SOCCER_FULLSTATE), the privileged setting adds the whole MuJoCo
state and the development rights (the full simulator, whole-match reset). Nothing of sports/soccer changes (H.7).
"""
from __future__ import annotations

SPORT = "soccer"
FORMAT = "match"
SEATS = ("A",)
ACTION_LEVEL = "low"                    # the joint level (12 leg joint targets per robot every 20 ms)
LEVELS = (1, 2, 3, 4, 5)                # sport.toml: the scripted levels and the learned teams (5: the twin's)
SOURCE_TASK = "soccer-match-wallclock-program-lowlevel-standard"
FAMILY = "soccer-jointcpu"
METADATA_FAMILY = "soccer_jointmatch"   # the twin's [metadata] family
ROBOT = "booster-t1"
INSTANCES = {"i01": {"level": 5, "seed": 101}}
SLOWDOWN = 10                           # the twin's RO_SLOWDOWN
CUTOFF_S = 14400                        # the twin's [agent] timeout_sec
EVERY = 1                               # a view every control step (20 ms of game time)
MAX_COMMANDS = 2                        # one command per robot per view
READY_TIMEOUT_S = 300                   # the twin's READY_TIMEOUT_S
REPLAY_TIMEOUT_S = 600                  # the twin's RO_REPLAY_TIMEOUT_S
VIDEO_TIMEOUT_S = 1800                  # the twin's RCB_VIDEO_TIMEOUT_S
# two halves of 300 s of game time at S = 10 are 6000 s of wall time; stoppages, a shoot-out and the service's lag
MATCH_WALL_S = 10800
IMAGE = "ghcr.io/mll-lab-nu/efe:embodied-olympics-match-soccer-0.1.0@sha256:b6fbfae73399a7daee9c623eb34cfe18de63b458349b5a2b9d122c00e9f1602b"
RESOURCES = {"min_cpus": 6.0, "min_memory_gb": 16.0, "verifier_min_cpus": 6.0, "verifier_min_memory_gb": 12.0}
DESCRIPTION = "humanoid robot soccer 2 v 2 at the joint level (coach format) against the learned joint-level team, CPU tier"
TRUTH_DOC = '`view["truth"]` is the state of the formal match at the step of the view, nothing later, in your team\'s frame (you\nattack +x): `ball` [x, y, z] and `ball_v`, `robots` (`us1`, `us2`, `them1`, `them2`: x, y, yaw, fallen, bench) - the\nsame fields as the twin\'s observation `truth` - plus `k` (control step) and `qpos`, `qvel` (the whole MuJoCo state:\nall four robots\' joints and the ball). `view["state"]` is the twin\'s observation: per robot of yours its joint state\n(joint_pos, joint_vel, trunk_quat, gyro, ...), the referee, the stoppages.'
NOTES_DOC = 'The joint level: per robot (entity "1", "2") `{"type": "joints", "q": [12 leg joint targets, rad]}` for the next 20 ms\ncontrol step, or `{"type": "traj", "k0": K, "q": [[12], ...]}`; each row is limited to the joint speed and ranges,\nthen PD every 2 ms, then the motors (`Session.spec()`: joint_level). A view comes every control step (20 ms of game\ntime, 0.2 s of wall time at S = 10); answer with up to 2 commands (one per robot). The opponent, level 5, is the\ntwin\'s learned joint-level team (sports/soccer/rl_joint.py, rl/joint/v2; numpy). Your program runs in the verifier on\nthe CPU with 2 GiB of address space: deploy what you learn as numpy (or plain Python) inference.\n\nResource tier: CPU only (6 cores, no GPU, no ML framework installed: numpy, SciPy and MuJoCo); the twin\'s seat toolkit\nis at `/opt/robot`. The twin `embodied-olympics-match-soccer-jointgpu-i01-privileged` is the same task with one NVIDIA\nGPU and a GPU training stack added; the formal match is the same in both tiers.'


def truth(match):
    w = match.w
    out = dict(w.truth_full("A"))       # the twin's own full-state field (its observation's `truth`), team A's frame
    out.update(k=int(w.k), qpos=[float(x) for x in w.d.qpos], qvel=[float(x) for x in w.d.qvel])
    return out
