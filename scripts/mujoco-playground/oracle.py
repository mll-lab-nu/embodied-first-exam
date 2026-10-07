"""Reference trajectories: a policy run closed loop on the frozen instance in the task's own MuJoCo, its targets recorded.

  python oracle.py <instance.json> --out traj.npz [--policy P]
Go1 joystick: MuJoCo Playground's own Go1 joystick policy (experimental/sim2sim/onnx/go1_policy.onnx @4057c14), with the
observation of play_go1_joystick.py (no noise): local linvel, gyro, gravity, q - home, qd, last action, command;
targets = home + 0.5 * action. Getup and the other tasks: a policy trained here (train/), TorchScript, observation as
in its env (train/qenv.py). Policies are used only to make the reference; no task image contains one.
Prints the replayed verdict of the recorded trajectory (a fresh Session), which is what the oracle check needs."""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared"))
import rcb_quadruped as Q  # noqa: E402

# A MuJoCo Playground checkout at 4057c14 (its pretrained Go1 policy); never part of a task image.
GO1_ONNX = os.path.join(os.environ.get("RCB_PLAYGROUND", "playground"), "mujoco_playground/experimental/sim2sim/onnx/go1_policy.onnx")


def f32(row) -> np.ndarray:
    """Every reference row is exactly representable in float32: the standard client sends actions as float32, so the
    privileged replay and the standard episode then execute the very same targets."""
    return np.asarray(row, dtype=np.float32).astype(np.float64)


def go1_joystick(s: Q.Session) -> np.ndarray:
    import onnxruntime as ort
    sess = ort.InferenceSession(GO1_ONNX, providers=["CPUExecutionProvider"])
    name = sess.get_inputs()[0].name
    last = np.zeros(12, np.float32)
    rows = []
    while not s.done:
        d = s.data
        obs = np.concatenate([s.sensor("local_linvel"), s.sensor("gyro"), s.gravity(), d.qpos[7:] - s.home, d.qvel[6:],
                              last, s.command_now()]).astype(np.float32)
        a = sess.run(None, {name: obs[None]})[0][0]
        last = a.astype(np.float32)
        row = f32(s.home + 0.5 * a)
        rows.append(row)
        s.step(row)
    return np.array(rows)


def torch_policy(s: Q.Session, path: str, obs_fn, act_fn, stop_fn=None) -> np.ndarray:
    import torch
    pol = torch.jit.load(path).eval()
    last = np.zeros(12)
    rows = []
    while not s.done:
        o = obs_fn(s, last)
        with torch.no_grad():
            a = np.clip(pol(torch.as_tensor(o, dtype=torch.float32)[None])[0].numpy().astype(np.float64), -1, 1)
        row = f32(act_fn(s, a))
        last = a
        rows.append(row)
        s.step(row)
        if stop_fn and stop_fn(s):
            break
    return np.array(rows)


def go1_getup_obs(s, last):
    d = s.data
    return np.concatenate([s.sensor("gyro"), s.gravity(), d.qpos[7:] - s.home, d.qvel[6:], last])


def go1_getup_act(s, a):
    return s.data.qpos[7:] + 0.5 * a                  # getup.py: current joints + 0.5 * action


def spot_getup_obs(s, last):
    return np.concatenate([s.sensor("gyro"), s.sensor("upvector"), s.data.qpos[7:] - s.home, last])


def spot_getup_act(s, a):
    return np.clip(s.data.qpos[7:] + 0.6 * a, s.lower, s.upper)   # spot/getup.py: current joints + 0.6 * action, clipped


def stand_on_two_policy(s: Q.Session, path: str) -> np.ndarray:
    """go1/handstand.py's policy, closed loop: observation local linvel, gyro, gravity, q - home, qd, last action;
    targets accumulate as Playground's do (ctrl + 0.3 * action, kept unclipped; the tooling clips what it applies, as
    MuJoCo clamps ctrl). Stops once the hold is complete."""
    import torch
    pol = torch.jit.load(path).eval()
    last = np.zeros(12)
    acc = s.targets.copy()
    rows = []
    while not s.done:
        d = s.data
        o = np.concatenate([s.sensor("local_linvel"), s.sensor("gyro"), s.gravity(), d.qpos[7:] - s.home, d.qvel[6:], last])
        with torch.no_grad():
            a = np.clip(pol(torch.as_tensor(o, dtype=torch.float32)[None])[0].numpy().astype(np.float64), -1, 1)
        acc = acc + 0.3 * a
        last = a
        rows.append(f32(np.clip(acc, s.lower, s.upper)))
        s.step(rows[-1])
        if s.check()["success"] or s.fell_at:
            break
    return np.array(rows)


class JoystickObs:
    """The observation the queue-trained joystick policies saw (train/qenv.py), without noise, built step by step."""

    def __init__(self, s: Q.Session, scale: float, lo, hi):
        self.s, self.scale, self.lo, self.hi = s, scale, np.asarray(lo), np.asarray(hi)
        self.last = np.zeros(12)
        self.motor = np.zeros(12)
        self.err = np.zeros(36)
        self.hist = np.zeros(15 * 31)

    def act(self, a) -> np.ndarray:
        self.motor = np.clip(self.s.home + a * self.scale, self.lo, self.hi)
        self.last = a
        return self.motor

    def spot(self) -> np.ndarray:                     # spot/joystick.py state (81)
        s = self.s
        q = s.data.qpos[7:]
        self.err = np.roll(self.err, 12)
        self.err[:12] = q - self.motor
        feet = np.concatenate([s.sensor(f"{f}_pos") for f in s.robot["feet"]])
        return np.concatenate([s.sensor("gyro"), s.sensor("upvector"), q - s.home, self.err, feet, self.last, s.command_now()])

    def spot_gait(self) -> np.ndarray:                # spot/joystick_gait_tracking.py state (69)
        s, g = self.s, self.s.gait
        q = s.data.qpos[7:]
        self.err = np.roll(self.err, 12)
        self.err[:12] = q - self.motor
        ph = np.fmod(np.asarray(g["phase0"]) + s.steps * g["phase_dt"] + np.pi, 2 * np.pi) - np.pi
        return np.concatenate([s.sensor("gyro"), s.sensor("upvector"), q, self.err, s.foot_contacts(), np.cos(ph), np.sin(ph),
                               [g["frequency_hz"], g["type"], g["foot_height_m"]]])

    def spot_gait_cmd(self) -> np.ndarray:            # the reference's policy: Playground's 69 + the command
        return np.concatenate([self.spot_gait(), self.s.command_now()])

    def barkour(self) -> np.ndarray:                  # barkour/joystick.py state: 15 frames of 31, newest first
        s = self.s
        o = np.concatenate([s.sensor("gyro")[2:3] * 0.25, s.sensor("upvector"), s.command_now() * np.array([2.0, 2.0, 0.25]),
                            s.data.qpos[7:] - s.home, self.last])
        self.hist = np.roll(self.hist, o.size)
        self.hist[:o.size] = np.clip(o, -100, 100)
        return self.hist.copy()


JOYSTICK = {   # env -> (action scale, limits(s) -> (lo, hi), observation builder)
    "SpotFlatTerrainJoystick": (0.3, lambda s: (s.lower, s.upper), JoystickObs.spot),
    "SpotJoystickGaitTracking": (0.6, lambda s: (s.lower, s.upper), JoystickObs.spot_gait_cmd),
    "BarkourJoystick": (0.3, lambda s: (np.tile([-0.7, -1.0, 0.05], 4), np.tile([0.52, 2.1, 2.1], 4)), JoystickObs.barkour),
}


def joystick_policy(s: Q.Session, path: str) -> np.ndarray:
    import torch
    pol = torch.jit.load(path).eval()
    scale, lim, build = JOYSTICK[s.env]
    ob = JoystickObs(s, scale, *lim(s))
    rows = []
    while not s.done:
        o = build(ob)
        with torch.no_grad():
            a = np.clip(pol(torch.as_tensor(o, dtype=torch.float32)[None])[0].numpy().astype(np.float64), -1, 1)
        rows.append(f32(ob.act(a)))
        s.step(rows[-1])
        if s.fell_at:
            break
    return np.array(rows)


def getup_stop(s):
    return s.check()["success"]                        # end the trajectory once the hold is complete


def getup_flip_then_stand(s: Q.Session, path: str, obs_fn, act_fn, flip_max: int = 200, stand_steps: int = 50) -> np.ndarray:
    """The trained getup policies turn the robot belly-down and level but stop there, crouched (a local optimum of
    Playground's getup reward). So: the policy until the trunk is level (tilt < 8 deg) and still (base speeds < 0.3) for
    20 steps in a row, then the joint targets interpolated linearly to the home pose over stand_steps, then held until
    the success hold is complete."""
    import torch
    pol = torch.jit.load(path).eval()
    last = np.zeros(12)
    rows = []
    calm = 0
    while s.steps < flip_max:
        o = obs_fn(s, last)
        with torch.no_grad():
            a = np.clip(pol(torch.as_tensor(o, dtype=torch.float32)[None])[0].numpy().astype(np.float64), -1, 1)
        row = f32(act_fn(s, a))
        last = a
        rows.append(row)
        s.step(row)
        calm = calm + 1 if (s.log[-1][2] < 8 and np.abs(s.data.qvel[:6]).max() < 0.3) else 0
        if calm >= 20:
            break
    q0 = s.targets.copy()
    for i in range(1, stand_steps + 1):
        rows.append(f32(q0 + (s.home - q0) * i / stand_steps))
        s.step(rows[-1])
    while not s.check()["success"] and not s.done:
        rows.append(f32(s.home))
        s.step(rows[-1])
    return np.array(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("instance")
    ap.add_argument("--out")
    ap.add_argument("--policy")
    a = ap.parse_args()
    os.environ["RCB_AGENT_TRACE_DIR"] = ""
    s = Q.Session(a.instance, check_hash=False)
    if s.env.startswith("Go1Joystick"):
        rows = go1_joystick(s)
    elif s.env == "Go1Getup":
        rows = getup_flip_then_stand(s, a.policy, go1_getup_obs, go1_getup_act)
    elif s.env == "SpotGetup":
        rows = torch_policy(s, a.policy, spot_getup_obs, spot_getup_act, getup_stop)
    elif s.env in ("Go1Handstand", "Go1Footstand"):
        rows = stand_on_two_policy(s, a.policy)
    elif s.env in JOYSTICK:
        rows = joystick_policy(s, a.policy)
    else:
        raise SystemExit(f"no reference for {s.env}")
    r = Q.Session(a.instance, check_hash=False).replay(rows)
    if a.out:
        np.save(a.out, rows)
    print(json.dumps({"instance": a.instance, "n_rows": len(rows), **{k: v for k, v in r.items() if k != "segments"},
                      "segments": r.get("segments")}))


if __name__ == "__main__":
    main()
