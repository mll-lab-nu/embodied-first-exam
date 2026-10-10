#!/usr/bin/env python3
"""Facts of the frozen MyoSuite instances, for the generator: instances/<family>.json from instances/<family>.npz.

Runs INSIDE the MyoSuite base image (it loads each instance and reads MyoSuite's own code and parameters):
  docker run --rm --network none --user $(id -u):$(id -g) -e HOME=/tmp -v $PWD:/repo -w /repo \\
      ghcr.io/mll-lab-nu/eai-myosuite:$(cat images/myosuite/VERSION) python scripts/myosuite/make_facts.py

An instance is the family's MyoSuite env after `seed(0)` and `reset(seed=0)` (`rcb_myosuite.py make-instance`); the npz
files are the ones every task of this benchmark was built and run on. The facts are the numbers and texts the task
texts quote (goal thresholds, hold time, MyoSuite's reward code for the privileged instruction, cameras, observation
keys). This script also checks that each instance rebuilds to its recorded state hash in this image and that the
relaxed limb (every muscle at rest for 400 control steps) does not succeed; with --oracles, that every reference in
oracles/ succeeds from its instance in two fresh sessions with the same final state. The generator (generate.py) needs
only these JSON files and the standard library.
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
import textwrap
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
os.environ["RCB_SESSION_LOG"] = ""
import numpy as np  # noqa: E402
import rcb_myosuite as M  # noqa: E402

M_TT_MAX = 3.0  # tabletennis_v0.MAX_TIME

M.SESSION_LOG = ""

# goal text: the standard twin never sees the code, so it must be complete. {..} fields are filled from the env.
FAMILIES: dict[str, dict] = {
    "key_turn": dict(
        goal=(
            "Turn the key held between the thumb and the index finger by more than {goal_th:.2f} rad (half a turn). "
            "Success: the key's hinge angle above {goal_th:.2f} rad for {hold} consecutive control steps ({hold_s} s). "
            "Failure (the episode ends): the index or thumb tip more than 0.10 m from the key head."
        ),
        scene="The key sits in a lock in front of the palm; its head is between the thumb and the index finger.",
        difficulty="medium",
        hours=1.5,
    ),
    "obj_hold": dict(
        goal=(
            "Hold the object at the goal: its centre within 0.010 m of the goal site for {hold} consecutive control steps "
            "({hold_s} s). Failure (the episode ends): the object more than 0.30 m from the goal (dropped). The object "
            "starts resting in the hand and falls if the hand does not grip it."
        ),
        scene="A small object rests in the palm of the upturned hand; the goal site is right above it.",
        difficulty="medium",
        hours=1.5,
    ),
    "pen_twirl": dict(
        goal=(
            "Rotate the pen in the hand until its axis points along the target orientation: the cosine between the pen's "
            "axis (bottom to top) and the target's axis above 0.95, with the pen within 0.075 m of its desired position, "
            "for {hold} consecutive control steps ({hold_s} s). Failure (the episode ends): the pen more than 0.075 m "
            "from its desired position (dropped)."
        ),
        scene="A pen lies across the fingers of the upturned hand; a translucent target pen shows the goal orientation.",
        difficulty="hard",
        hours=3.0,
    ),
    "die_reorient": dict(
        goal=(
            "Rotate the die in the hand to the target pose: its position within {pos_th} m of the target and the norm of "
            "its Euler-angle error below {rot_th} rad, for {hold} consecutive control steps ({hold_s} s). Failure (the "
            "episode ends): the die more than {drop_th} m from the target (dropped)."
        ),
        scene="A die rests in the palm of the upturned hand; a translucent target die shows the goal orientation.",
        difficulty="hard",
        hours=3.0,
    ),
    "baoding": dict(
        goal=(
            "Baoding balls: rotate the two balls around each other in the palm so that each follows its moving target "
            "(the targets circle the palm once every {period} s). Success: both balls within {proximity_th} m of their "
            "targets for {hold} consecutive control steps ({hold_s} s: one full orbit of the targets). Failure (the episode ends): a ball's height (world z) "
            "drops below {drop_th} m, i.e. it falls out of the palm."
        ),
        scene="Two balls rest in the palm of the upturned hand; two small markers show where each ball should be now.",
        difficulty="hard",
        hours=3.0,
    ),
    "hand_reach": dict(
        goal=(
            "Move all five fingertips onto their targets: the norm of the stacked fingertip-to-target errors (5 tips x 3 "
            "coordinates) below {near_th:.4f} m, for {hold} consecutive control steps ({hold_s} s). Failure (the episode "
            "ends, from the third control step on): that norm above {far_total:.3f} m."
        ),
        scene="The hand hangs relaxed; five small spheres mark where the thumb, index, middle, ring and little fingertips must go.",
        difficulty="easy",
        hours=1.0,
    ),
    "hand_pose": dict(
        goal=(
            "Put the hand in the target pose: the norm of the 23 hand and wrist joint-angle errors (rad) below {pose_thd} "
            "for {hold} consecutive control steps ({hold_s} s). Failure (the episode ends): that norm above {pose_far:.2f} "
            "rad. The target joint angles are given below."
        ),
        scene="The hand starts in its rest posture; translucent markers show where the five fingertips are in the target pose.",
        difficulty="medium",
        hours=1.5,
    ),
    "obj_reorient": dict(
        goal=(
            "Reorient the object held in the hand to the target orientation: the cosine between the object's orientation "
            "vector and the target's above 0.95, with the object within 0.075 m of the target position, for {hold} "
            "consecutive control steps ({hold_s} s). Failure (the episode ends): the object more than 0.075 m from the "
            "target position (dropped)."
        ),
        scene="An object (one of eight shapes; this instance fixes one) rests on the fingers of the upturned hand; a translucent copy shows the target orientation.",
        difficulty="hard",
        hours=3.0,
    ),
    "arm_reach": dict(
        goal=(
            "Bring the index fingertip to the target point in space: its distance below {near_th:.4f} m for {hold} "
            "consecutive control steps ({hold_s} s). Failure (the episode ends, from the third control step on): the "
            "distance above {far_total:.2f} m."
        ),
        scene="The arm hangs at the side; a small sphere in front of the body marks the target for the index fingertip.",
        difficulty="medium",
        hours=1.5,
    ),
    "relocate": dict(
        goal=(
            "Pick up the object from the table and put it in the target receptacle: the object's position within "
            "{pos_th} m of the target (rotation is ignored) for {hold} consecutive control steps ({hold_s} s). Failure "
            "(the episode ends): the palm more than {drop_th} m from the object."
        ),
        scene="An object stands on the table in front of the arm; a receptacle marks the target position.",
        difficulty="hard",
        hours=3.0,
    ),
    # ---- set 3 (2026-10-06): a sarcopenia variant, five MyoChallenge tasks, six MyoDex object-motion tasks
    "sarc_key_turn": dict(goal="", scene="As key_turn: the key sits in a lock in front of the palm, its head between the thumb and the index finger.",
                          difficulty="hard", hours=2.0),
    "table_tennis": dict(goal="", scene="You stand at a table-tennis table holding a paddle in the right hand; a ball is served toward you from the far side.",
                         difficulty="hard", hours=4.0),
    "bimanual": dict(goal="", scene="The MyoArm (right, muscles) and a prosthetic MPL arm (left, motors) stand at a table; an object lies in front of the MyoHand and a pillar marks the goal on the far side.",
                     difficulty="hard", hours=4.0),
    "soccer": dict(goal="", scene="A musculoskeletal body with two legs stands on a soccer pitch; a ball lies in front of it and a goalkeeper guards the goal.",
                   difficulty="hard", hours=5.0),
    # the frozen instance drew the opponent policy `stationary` (MyoChallenge draws it once per environment): it stands still
    "chase_tag": dict(goal="", scene="A musculoskeletal body with two legs stands in a square arena; an opponent stands somewhere in it (in this frozen instance it does not move).",
                      difficulty="hard", hours=5.0),
    "osl_run": dict(goal="", scene="A musculoskeletal body whose left leg is an Open-Source Leg prosthesis (knee and ankle motors driven by its own controller) stands at the start of a straight, flat running track.",
                    difficulty="hard", hours=5.0),
    "dex_apple_lift": dict(goal="", scene="An apple lies on the table; the MyoHand (with a 6-DoF positioned wrist) is at its pre-grasp pose next to it.", difficulty="hard", hours=3.0,
                           skill="lift", obj="apple"),
    "dex_cylinder_pass": dict(goal="", scene="A small cylinder lies on the table; the MyoHand is at its pre-grasp pose.", difficulty="hard", hours=3.0,
                              skill="pass (pick it up and present it for a hand-over)", obj="small cylinder"),
    "dex_bunny_inspect": dict(goal="", scene="The Stanford bunny lies on the table; the MyoHand is at its pre-grasp pose.", difficulty="hard", hours=3.0,
                              skill="inspect (lift it and turn it to look at it)", obj="Stanford bunny"),
    "dex_hammer_use": dict(goal="", scene="A hammer lies on the table; the MyoHand is at its pre-grasp pose.", difficulty="hard", hours=3.0,
                           skill="use (grasp it and swing it)", obj="hammer"),
    "dex_cup_pour": dict(goal="", scene="A cup stands on the table; the MyoHand is at its pre-grasp pose.", difficulty="hard", hours=3.0,
                         skill="pour (lift it and tilt it as if pouring)", obj="cup"),
    "dex_airplane_fly": dict(goal="", scene="A toy airplane lies on the table; the MyoHand is at its pre-grasp pose.", difficulty="hard", hours=3.0,
                             skill="fly (lift it and fly it through the air)", obj="toy airplane"),
}


def goal_text(fam: str, s) -> str:
    b = s.base
    vals = dict(
        hold=s.hold_steps,
        hold_s=round(s.hold_steps * s.dt, 3),
        goal_th=getattr(b, "goal_th", 0.0),
        pos_th=getattr(b, "pos_th", 0.0),
        rot_th=getattr(b, "rot_th", 0.0),
        drop_th=getattr(b, "drop_th", 0.0),
        proximity_th=getattr(b, "proximity_th", 0.0),
        period=getattr(b, "goal_time_period", [5])[0] if hasattr(b, "goal_time_period") else 5,
        near_th=0.0125 * len(getattr(b, "tip_sids", [0])),
        far_total=getattr(b, "far_th", 0.0) * len(getattr(b, "tip_sids", [0])),
        pose_thd=getattr(b, "pose_thd", 0.0),
        pose_far=4 * 3.141592653589793 / 2,
    )
    text = FAMILIES[fam]["goal"].format(**vals)
    if fam == "hand_pose":  # the standard twin never sees the env: spell the target out
        import mujoco

        names = [mujoco.mj_id2name(s.model, mujoco.mjtObj.mjOBJ_JOINT, i) for i in range(s.model.njnt)]
        text += (
            " Target joint angles (rad): "
            + ", ".join(f"{n} {float(v):+.3f}" for n, v in zip(names, b.target_jnt_value))
            + "."
        )
    return text


def goal_text_set3(fam: str, s) -> str:
    b = s.base
    if fam == "sarc_key_turn":
        return (goal_text("key_turn", s) + " The muscles are sarcopenic: MyoSuite's sarcopenia condition halves every "
                "muscle's maximum isometric force.")
    if fam == "table_tennis":
        return ("Return the served ball: hit it with the paddle so that it lands on the opponent's half of the table "
                "(MyoChallenge 2025 TableTennis P1's own success test on the ball's contact history: after the serve's "
                "bounce on your half, the paddle touches it once, then it touches the opponent's half, with no second paddle "
                f"touch and no further bounce on your half). Failure (the episode ends): any other outcome of the rally, the ball "
                f"falling below 0.3 m, or {M_TT_MAX:g} s of simulated time.")
    if fam == "bimanual":
        return ("Hand the object over: pick it up with the MyoHand, pass it to the prosthetic hand, and place it on the goal "
                f"pillar. Success: the object within {b.proximity_th:g} m of the pillar top after touching only the pillar for "
                f"{b.TARGET_GOAL_TOUCH} control steps, and MyoChallenge 2024's contact check on its whole history passes (held by "
                "the MyoHand for at least 100 control steps, by the prosthesis for at least 100, only the pillar at the end, "
                "never the table or the floor). Failure (the episode ends): the object below 0.3 m (dropped), or 10 s of "
                "simulated time.")
    if fam == "soccer":
        return (f"Score a goal: kick the ball into the goal, past the goalkeeper, within {b.max_time:g} s of simulated time "
                "(MyoChallenge 2025 Soccer P1: the ball's centre crosses the goal line between the posts and under the bar). "
                "Failure (the episode ends): the pelvis below 0.2 m (fallen), or the time limit.")
    if fam == "chase_tag":
        return (f"Tag the opponent: bring your pelvis within {b.win_distance:g} m of it (horizontal distance) within "
                f"{b.maxTime:g} s of simulated time (MyoChallenge 2023 ChaseTag P1, task CHASE). Failure (the episode ends): "
                "the time limit, leaving the 13 x 13 m arena, or the pelvis below 0.5 m (fallen).")
    if fam == "osl_run":
        return (f"Run the track: move forward {b.start_pos - b.end_pos:g} m along it to the finish (MyoChallenge 2024 OSL "
                f"Run, its own win condition), staying within {b.real_width:g} m of the track's centre line and on your feet; "
                "the left leg is the prosthesis, driven by its own controller, so you command only the 54 muscles. Failure "
                "(the episode ends): falling, leaving the track sideways, or moving 2 m backwards. There is no time limit.")
    if fam.startswith("dex_"):
        f = FAMILIES[fam]
        rot = M.TRACK_ROT[fam]
        return (f"Move the {f['obj']} along MyoDex's recorded {f['skill']} motion: a reference of the object's pose over "
                f"{s.track_steps} control steps ({s.track_steps * s.dt:.2f} s), from GRAB motion capture (TCDM / MyoDex). "
                f"The episode lasts exactly those {s.track_steps} steps. Success: the object's motion follows the "
                f"reference's: its centre of mass's displacement since the start within {M.TRACK_POS_M:g} m of the "
                "reference's displacement since the reference's start" + (f", and its rotation since the start within "
                f"{M.TRACK_ROT_RAD:g} rad of the reference's" if rot else "") + f", at at least {M.TRACK_FRAC:.0%} of the "
                f"control steps and at the last one, with the displacement error never above {M.TRACK_MAX_M:g} m. "
                "Failure (the episode ends early): MyoDex's termination, the object more than 0.25 m from the reference or "
                "from the wrist.")
    raise KeyError(fam)


def reference_rel(s) -> list:
    """MyoDex: the reference object pose per control step, relative to the object's start (dx, dy, dz in the world's
    axes, m; orientation as a wxyz quaternion in the world frame): the goal of the task, given to both modes."""
    out = []
    p0 = np.asarray(s.base.obs_dict["curr_obj_com"]).reshape(-1)
    for k in range(s.track_steps + 1):
        r = s.base.ref.get_reference(k * s.dt + s.base.motion_start_time)
        o = np.asarray(r.object, dtype=np.float64).reshape(-1)
        out.append([round(k * s.dt, 4), *[round(float(x), 5) for x in (o[:3] - p0)], *[round(float(x), 5) for x in o[3:7]]])
    return out


def scene_cameras(s) -> list:
    """Cameras that are mounted on, track or are aimed at a body of the scene that is not the agent's own (a mocap body
    such as the opponent or the goalkeeper, or a body behind a joint that is not the body's): their pose is that body's
    position plus a constant, so the standard service gives their images only. The rule of shared/standard/server.py
    (`scene_camera`), repeated here for the task texts."""
    m = s.model
    own = {int(m.joint(j["name"]).id) for j in s.joints() if j["name"] != "keyjoint" and not j["name"].startswith("OBJ")}
    own |= {j for j in range(m.njnt) if int(m.jnt_type[j]) == 0 and m.joint(j).name == "root"}

    def own_body(b: int) -> bool:
        while b > 0:
            first = int(m.body_jntadr[b])
            if int(m.body_mocapid[b]) >= 0 or any(j not in own for j in range(first, first + int(m.body_jntnum[b]))):
                return False
            b = int(m.body_parentid[b])
        return True

    out = []
    for c in s.cameras():
        i = m.camera(c).id
        bodies = [int(m.cam_bodyid[i])] + ([int(m.cam_targetbodyid[i])] if int(m.cam_mode[i]) in (3, 4) else [])
        if not all(own_body(b) for b in bodies if b >= 0):
            out.append(c)
    return out


def facts(fam: str) -> dict:
    inst = HERE / "instances" / f"{fam}.npz"
    if not inst.exists():                      # a new family: freeze its instance (seed(0), reset(seed=0))
        M.Session(fam).save_instance(inst, {"source": f"{M.TASKS[fam]} after seed(0), reset(seed=0)", "myosuite": "2.12.2"})
    s = M.Session(fam, instance=inst)
    ref = reference_rel(s) if s.rule == "track" else None      # at the start of an episode
    s.reset()
    assert s.instance_exact, f"{fam}: the instance does not rebuild to its recorded state hash in this image"
    rest = np.tile(s.rest_action(), (400, 1))
    t0 = time.time()
    st = s.replay(rest)
    rate = st["replayed_rows"] / max(time.time() - t0, 1e-6)
    assert not st["success"], f"{fam}: the relaxed limb already succeeds: {st}"
    cls = type(s.base)
    path = Path(inspect.getsourcefile(cls)).as_posix().split("site-packages/")[-1]
    return {
        "family": fam,
        "env_id": s.env_id,
        "body": M.BODY[fam],
        "nu": s.nu,
        "dt": s.dt,
        "frame_skip": int(s.base.frame_skip),
        "hold_steps": s.hold_steps,
        "hold_s": round(s.hold_steps * s.dt, 3),
        "instance_sha": s.instance_sha,
        "goal": goal_text(fam, s) if fam in FAMILIES and FAMILIES[fam]["goal"] else goal_text_set3(fam, s),
        "rule": s.rule,
        "set3": fam in M.STATE_SET3,
        "actuators": [a for a in s.actuators() if a["kind"] != "muscle"],
        "n_muscles": sum(1 for a in s.actuators() if a["kind"] == "muscle"),
        "free_root": bool(any(s.model.jnt_type[j] == 0 and s.model.joint(j).name == "root" for j in range(s.model.njnt))),
        "track_steps": s.track_steps,
        "reference": ref,
        "scene": FAMILIES[fam]["scene"],
        "difficulty": FAMILIES[fam]["difficulty"],
        "hours": FAMILIES[fam]["hours"],
        "reward_path": path,
        "reward_src": textwrap.dedent(inspect.getsource(cls.get_reward_dict)).rstrip(),
        "obs_keys": [k for k in s.base.obs_dict if k != "time"],
        "cameras": s.cameras(),
        "scene_cameras": scene_cameras(s),
        "steps_per_s": int(round(rate, -2)),
        "rest_reason": st["reason"],
    }


def check_oracle(fam: str) -> dict:
    A = np.load(HERE / "oracles" / f"{fam}.npy")
    assert np.array_equal(A, A.astype(np.float32).astype(np.float64)), f"{fam}: reference rows are not float32-exact"
    runs = [M.Session(fam, instance=HERE / "instances" / f"{fam}.npz").replay(A) for _ in range(2)]
    assert all(r["success"] for r in runs) and runs[0]["state_sha"] == runs[1]["state_sha"], (fam, runs)
    return {
        "reference_rows": int(len(A)),
        "reference_steps": int(runs[0]["steps"]),
        "reference_sha": runs[0]["state_sha"],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("families", nargs="*", default=sorted(M.TASKS))
    ap.add_argument("--oracles", action="store_true", help="also re-check the references in oracles/")
    a = ap.parse_args()
    for fam in a.families:
        f = facts(fam)
        if (HERE / "oracles" / f"{fam}.npy").exists():
            old = HERE / "instances" / f"{fam}.json"
            prev = json.loads(old.read_text()) if old.exists() else {}
            f.update(
                check_oracle(fam)
                if a.oracles or "reference_rows" not in prev
                else {k: prev[k] for k in ("reference_rows", "reference_steps", "reference_sha")}
            )
        (HERE / "instances" / f"{fam}.json").write_text(json.dumps(f, indent=1) + "\n")
        print(fam, f["instance_sha"], f.get("reference_steps"), f["steps_per_s"], flush=True)


if __name__ == "__main__":
    main()
