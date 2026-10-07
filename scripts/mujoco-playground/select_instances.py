"""Pick and freeze each task's instance from make_instances.py's candidates, with a fixed rule that never looks at an
agent's result:

  joystick  seeds in order 0, 1, 2, ...; a candidate is skipped when its command schedule is mostly standstill (less than
            half of the episode commands |v_xy| >= 0.3 m/s or |w_z| >= 0.3 rad/s), when its pushes (Barkour) are null or
            weak (peak under 20% of the torso's weight), or when the reference trajectory (oracle.py) fails the task's
            success check; the first remaining seed is the instance.
  getup     seeds in order; skipped when Playground's reset did not drop the robot (it starts standing) or when, after the
            settle, the trunk is tilted less than 90 degrees (not fallen over), or when the reference fails; first remaining.
  stand     (hand/footstand) seeds in order; skipped when the reference fails; first remaining.

  python select_instances.py Go1JoystickFlatTerrain --cand <dir> [--policy P]
writes instances/<Env>.json (the frozen instance with its t = 0 state hash) and oracles/<Env>.npy (the reference
trajectory), and selection/<Env>.json (every candidate tried, with why it was skipped)."""
import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "shared"))
sys.path.insert(0, HERE)
import oracle  # noqa: E402
import rcb_quadruped as Q  # noqa: E402

TEXT = {
    "Go1JoystickFlatTerrain": "Make the Unitree Go1 follow the joystick command schedule on flat ground for the whole "
                              "20 s episode without falling over.",
    "Go1JoystickRoughTerrain": "Make the Unitree Go1 follow the joystick command schedule on rough terrain (a 20 x 20 m "
                               "heightfield, up to 5 cm high) for the whole 20 s episode without falling over.",
    "Go1Getup": "The Unitree Go1 has fallen over. Make it get up and stand upright at its standing height.",
    "SpotGetup": "Boston Dynamics Spot has fallen over. Make it get up and stand upright at its standing height.",
    "SpotFlatTerrainJoystick": "Make Boston Dynamics Spot follow the joystick command schedule on flat ground for the whole "
                               "20 s episode without falling over.",
    "SpotJoystickGaitTracking": "Make Boston Dynamics Spot follow the joystick command schedule for the whole 20 s episode with "
                                "the commanded gait (the feet's swing pattern, frequency and height) without falling over.",
    "BarkourJoystick": "Make Google's Barkour quadruped follow the joystick command schedule for the whole 10 s episode, "
                       "through random pushes, without falling over.",
    "Go1Handstand": "Make the Unitree Go1 do a handstand: balance on its front legs, nose down, hind legs in the air, for 2 s.",
    "Go1Footstand": "Make the Unitree Go1 stand up on its hind legs, nose up, front legs in the air, and balance there for 2 s.",
}


def activity(inst: dict) -> float:
    cmd = Q.schedule_of(inst, Q.ENVS[inst["env"]]["horizon"])
    return float(np.mean((np.linalg.norm(cmd[:, :2], axis=1) >= 0.3) | (np.abs(cmd[:, 2]) >= 0.3)))


def facts(s0: Q.Session, inst: dict, rows, r: dict) -> dict:
    """The numbers the task texts quote (generate.py reads them; it runs without MuJoCo)."""
    q = np.asarray(inst["qpos0"])
    w, z = q[3], q[6]
    out = {"start_xy_m": [round(float(q[0]), 3), round(float(q[1]), 3)],
           "start_yaw_deg": round(float(np.degrees(2 * np.arctan2(z, w))), 1),
           "start_tilt_deg": round(float(np.degrees(np.arccos(np.clip(s0.data.site_xmat[s0._imu][8], -1, 1)))), 1),
           "start_imu_height_m": round(float(s0.data.site_xpos[s0._imu][2]), 3),
           "reference_rows": int(len(rows)), "torso_mass_kg": round(s0._root_mass, 3)}
    for k in ("worst_lin_err", "worst_yaw_err", "worst_gait_err", "tilt_deg", "imu_height", "pose_angle_deg"):
        if r.get(k) is not None:
            out[f"reference_{k}"] = r[k]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("env")
    ap.add_argument("--cand", default="cand")
    ap.add_argument("--policy")
    ap.add_argument("--max", type=int, default=40)
    a = ap.parse_args()
    os.environ["RCB_AGENT_TRACE_DIR"] = ""
    os.environ["RCB_SESSION_LOG"] = ""
    for d in ("instances", "oracles", "selection"):
        os.makedirs(os.path.join(HERE, d), exist_ok=True)
    tried = []
    for k in range(a.max):
        path = os.path.join(a.cand, a.env, f"seed{k}.json")
        inst = json.load(open(path))
        inst["text"] = TEXT[a.env]
        rec = {"seed": k}
        if "commands" in inst:
            rec["activity"] = round(activity(inst), 3)
            if rec["activity"] < 0.5:
                tried.append({**rec, "skipped": "mostly standstill"})
                continue
            if "kicks" in inst:
                mass = Q.Session(path, check_hash=False)._root_mass
                peak = max((0.5 * mass * k["velocity_mps"] / (k["duration_steps"] * 0.02) if k["duration_steps"] >= 2 else 0.0)
                           for k in inst["kicks"])
                rec["push_peak_n"] = round(peak, 1)
                if peak < 0.2 * mass * 9.81:
                    tried.append({**rec, "skipped": "pushes null or weak (peak under 20% of the torso's weight; a 1-step "
                                                    "kick is zero in Playground's half-sine)"})
                    continue
        elif "dropped" in inst:
            if not inst["dropped"]:
                tried.append({**rec, "skipped": "not dropped (starts standing)"})
                continue
            tilt = Q.Session(path, check_hash=False).state()
            rec["start_tilt_deg"] = round(float(np.degrees(np.arccos(np.clip(tilt["imu_mat"][2, 2], -1, 1)))), 1)
            if rec["start_tilt_deg"] < 90:
                tried.append({**rec, "skipped": "tilted less than 90 degrees after the settle"})
                continue
        s = Q.Session(path, check_hash=False)
        if a.env.startswith("Go1Joystick"):
            rows = oracle.go1_joystick(s)
        elif a.env == "Go1Getup":
            rows = oracle.getup_flip_then_stand(s, a.policy, oracle.go1_getup_obs, oracle.go1_getup_act)
        elif a.env == "SpotGetup":
            rows = oracle.torch_policy(s, a.policy, oracle.spot_getup_obs, oracle.spot_getup_act, oracle.getup_stop)
        elif a.env in ("Go1Handstand", "Go1Footstand"):
            rows = oracle.stand_on_two_policy(s, a.policy)
        elif a.env in oracle.JOYSTICK:
            rows = oracle.joystick_policy(s, a.policy)
        r1 = Q.Session(path, check_hash=False).replay(rows)
        r2 = Q.Session(path, check_hash=False).replay(rows)
        keep = {k2: r1[k2] for k2 in ("success", "fell_at", "worst_lin_err", "worst_yaw_err", "tilt_deg", "imu_height", "pose_angle_deg",
                                      "steps") if k2 in r1}
        if not (r1["success"] and r2["success"] and r1["state_sha"] == r2["state_sha"]):
            tried.append({**rec, **keep, "skipped": "reference fails"})
            continue
        s0 = Q.Session(path, check_hash=False)
        inst["facts"] = facts(s0, inst, rows, r1)
        inst["state_sha"] = s0.state_sha()
        inst["horizon"] = s0.horizon
        inst["selection"] = {"rule": __doc__.split("\n\n")[1].strip(), "candidates_tried": len(tried) + 1}
        json.dump(inst, open(os.path.join(HERE, "instances", f"{a.env}.json"), "w"), indent=1)
        np.save(os.path.join(HERE, "oracles", f"{a.env}.npy"), rows)
        tried.append({**rec, **keep, "chosen": True})
        json.dump({"env": a.env, "candidates": tried}, open(os.path.join(HERE, "selection", f"{a.env}.json"), "w"), indent=1)
        print(json.dumps({"env": a.env, "seed": k, "state_sha": inst["state_sha"], "n_rows": len(rows), **keep}))
        return
    json.dump({"env": a.env, "candidates": tried}, open(os.path.join(HERE, "selection", f"{a.env}.json"), "w"), indent=1)
    raise SystemExit(f"{a.env}: no candidate among the first {a.max} seeds")


if __name__ == "__main__":
    main()
