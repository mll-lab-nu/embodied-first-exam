"""Build the frozen DexJoCo instances and their reference trajectories, and record the facts the task texts quote.

Runs INSIDE the base image (DexJoCo + MuJoCo); writes scripts/dexjoco/instances/<family>/:
  instance.npz            the frozen scene (rcb_dexjoco.Session.save_instance)
  oracle_trajectory.npz   the human demonstration's own actions, truncated where its episode ends in success
  facts.json              what generate.py needs from the simulator (cameras, start targets, hand limits, the upstream
                          success code, the arm bases, the table height, the oracle's length and margin)

  # 1. the demos (public Hugging Face dataset DexJoCo/DexJoCo-Datasets-Raw, replay.zarr only, ~120 KB each)
  python3 scripts/dexjoco/get_demo.py water_plant 1 /tmp/demos
  # 2. in the image, from the repo root
  docker run --rm --user $(id -u):$(id -g) -e HOME=/tmp -v $PWD:/repo -v /tmp/demos:/demos -w /repo \
      ghcr.io/mll-lab-nu/eai-dexjoco:0.1.2 python scripts/dexjoco/make_instances.py water_plant \
      --demo /demos/water_plant/<demo>/replay.zarr
  # without --demo: keep the committed instance and oracle, check them and refresh facts.json only
  docker run ... python scripts/dexjoco/make_instances.py --all

Instance = the task's env after reset with the initial object poses and table height of the demonstration restored
(DexJoCo's own state restorer, demo state[0]). The reference = the demonstration's actions replayed through the tooling
until its episode ends in success; a demo that does not succeed from its own initial state is refused. The rows are
float32-exact (the standard-mode client sends float32), checked here.
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
import rcb_dexjoco as R  # noqa: E402

R.SESSION_LOG = ""
# family -> (the upstream methods that decide success, the demonstration used for the instance)
FAMILIES = {
    "water_plant": (["_compute_success"], "water_plant_demo_10_2026-02-05_19-50-27_886249"),
    "click_mouse": (["_compute_success", "_mouse_in_mousepad", "_detect_click"], "monitor_mousepad_demo_10_2026-03-10_20-07-29_950914"),
    "hammer_nail": (["_compute_success", "_apply_hammer_nail_interaction"], "hammer_nail_demo_10_2026-02-05_19-18-55_029010"),
    "bimanual_hanoi": (["_compute_success_metrics", "_compute_success"], "hanoi_demo_10_2026-03-13_15-45-06_925668"),
    "pick_bucket": (["_compute_success"], "bucket_pick_demo_10_2026-03-10_18-19-00_120725"),
    "pinch_tongs": (["_compute_success", "_update_pinch_count"], "table_tongs_demo_10_2026-03-12_16-30-04_442884"),
    "fold_glasses": (["_compute_success"], "glass_fold_demo_10_2026-03-11_20-33-55_671576"),
    "bimanual_microwave_cook": (["_compute_success", "hot_dog_inside_microwave"], "microwave_cook_demo_10_2026-02-09_11-56-09_655851"),
    "bimanual_unlock_ipad": (["_compute_success"], "ipad_unlock_demo_10_2026-03-22_13-59-49_595064"),
    "bimanual_assembly": (["_compute_success", "_compute_success_metrics"], "assembly_demo_10_2026-03-19_17-36-54_867270"),
    "bimanual_photograph": (["_compute_success", "_compute_success_metrics"], "photograph_demo_10_2026-03-16_14-31-13_305518"),
}
RCB_CODE = {"water_plant": ["water_aim_deg"]}       # robot_coding_bench's tightened checks, quoted in the instruction


def success_source(s: R.Session, fam: str) -> tuple[str, str]:
    cls = type(s.base)
    src = "\n".join(textwrap.dedent(inspect.getsource(getattr(cls, m))) for m in FAMILIES[fam][0])
    return src.rstrip(), str(Path(inspect.getsourcefile(cls)).relative_to("/opt/dexjoco"))


def build_from_demo(fam: str, demo: str, out: Path) -> None:
    import zarr
    from dexjoco.tasks.state_restorers import restore_initial_state
    s = R.Session(fam)
    root = zarr.open(demo, mode="r")
    s.base.reset()
    restore_initial_state(s.env, fam, s.cfg, np.asarray(root["data"]["state"][0]).ravel())
    s._snapshot = s.snapshot(); s._episode_reset()
    s.save_instance(out / "instance.npz", {"source": "DexJoCo-Datasets-Raw demo initial state (dexjoco.tasks.state_restorers)",
                                           "demo": FAMILIES[fam][1], "dexjoco": "8d23b0f"})
    A = np.asarray(root["data"]["action"], dtype=np.float64)
    s2 = R.Session(fam, instance=out / "instance.npz")
    st = s2.replay(A)
    if not st["success"]:
        raise SystemExit(f"{fam}: the demo does not succeed from its own initial state: {st}")
    s2.save_trajectory(A[:st["replayed_rows"]], out / "oracle_trajectory.npz", {"source": "demo actions", "demo": FAMILIES[fam][1]})
    # facts() rounds the rows to float32 (and checks they still succeed) if they are not float32-exact


def scene_cameras(s) -> list:
    """Cameras that are mounted on, track or are aimed at a body that is neither fixed in the world nor moved by the
    robot's own joints alone (a mocap body, or a body behind an object's joint: in bimanual_photograph `cam_pos_z`, the
    lens of the camera the hands pick up): their pose is that object's pose, so the standard service gives their images
    only. The rule of shared/standard/server.py (`scene_camera`), repeated here for the task texts;
    tests/test_standard_server.py checks the committed facts against the frozen instances' models."""
    m = s.model
    own = set()                                       # the arms' and the hands' joints, as the service names them
    for a in s.arms():
        sfx = f"_{a}" if s.bimanual else ""
        own |= {int(m.joint(f"joint{i}{sfx}").id) for i in range(1, 8)}
        own |= {int(m.actuator_trnid[i, 0]) for i in s._hand_ctrl_ids(a)}

    def own_body(b: int) -> bool:
        while b > 0:
            if int(m.body_mocapid[b]) >= 0:
                return False
            first = int(m.body_jntadr[b])
            if any(j not in own for j in range(first, first + int(m.body_jntnum[b]))):
                return False
            b = int(m.body_parentid[b])
        return True

    out = []
    for name in s.cameras():
        i = m.camera(name).id
        bodies = [int(m.cam_bodyid[i])] + ([int(m.cam_targetbodyid[i])] if int(m.cam_mode[i]) in (3, 4) else [])
        if not all(own_body(b) for b in bodies if b >= 0):
            out.append(name)
    return out


def facts(fam: str, out: Path) -> dict:
    inst = out / "instance.npz"
    A = np.asarray(np.load(out / "oracle_trajectory.npz")["actions"], dtype=np.float64)
    s = R.Session(fam, instance=inst)
    if not np.array_equal(A.astype(np.float32).astype(np.float64), A):
        # the standard client sends float32: round the demo's rows to float32 (both modes use the same reference), keep
        # them only if they still succeed (holding the last row up to 5 s more if the episode has not ended), truncated
        # where the episode ends
        A = A.astype(np.float32).astype(np.float64); n_demo = len(A)
        st = s.replay(A)
        if not st["done"]:          # the rounded rows end a few steps short of the hold count: hold the last row
            A = np.concatenate([A, np.repeat(A[-1:], 250, axis=0)])
            st = s.replay(A)
        if not st["success"]:
            raise SystemExit(f"{fam}: the demo rows rounded to float32 do not succeed: {st}")
        A = A[:st["replayed_rows"]]
        meta = json.loads(str(np.load(out / "oracle_trajectory.npz")["meta"]))
        s.save_trajectory(A, out / "oracle_trajectory.npz", {**meta, "float32": True, "demo_rows": int(n_demo)})
        print(f"{fam}: oracle rows rounded to float32 ({len(A)} rows)", flush=True)
    if not s.instance_exact:
        raise SystemExit(f"{fam}: this image does not rebuild the instance (state sha {s.state_sha()} != {s.instance_sha})")
    t0 = time.time(); st = s.replay(A); dt = time.time() - t0
    if not st["success"] or st["replayed_rows"] != len(A):
        raise SystemExit(f"{fam}: the oracle does not end in success on its last row: {st}")
    st2 = R.Session(fam, instance=inst).replay(A)
    assert st2["state_sha"] == st["state_sha"], (st, st2)
    bim = s.bimanual
    s.reset()
    tgt = s.hold_action()
    fmt = lambda v, n: [round(float(x), n) for x in v]  # noqa: E731
    tcp0 = (f"right {fmt(tgt[:3], 3)} / {fmt(tgt[3:7], 4)}, left {fmt(tgt[23:26], 3)} / {fmt(tgt[26:30], 4)}" if bim
            else f"{fmt(tgt[:3], 3)} / {fmt(tgt[3:7], 4)}")
    try:
        table_z = round(float(s.data.site("table_top").xpos[2]), 3)
    except KeyError:
        table_z = None
    bases = {n: fmt(s.body_pose(n)[0], 3) for n in s.bodies() if n.startswith("link0")}
    src, path = success_source(s, fam)
    rcb_src = "\n".join(textwrap.dedent(inspect.getsource(getattr(R, n))) for n in RCB_CODE.get(fam, [])).rstrip()
    return {"family": fam, "demo": FAMILIES[fam][1], "instance_sha": s.instance_sha, "objects": list(s.objects()),
            "cameras": s.cameras(), "scene_cameras": scene_cameras(s), "tcp0": tcp0, "table_top_z": table_z, "arm_bases": bases,
            "hand_lo": fmt(s.hand_limits()[:, 0], 2), "hand_hi": fmt(s.hand_limits()[:, 1], 2),
            "oracle_rows": int(len(A)), "oracle_state_sha": st["state_sha"],
            "steps_per_s": int(round(len(A) / max(dt, 1e-6), -1)),
            "success_src": src, "success_path": path, "rcb_src": rcb_src, "water_aim_max_deg": R.WATER_AIM_MAX_DEG}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("families", nargs="*"); ap.add_argument("--all", action="store_true"); ap.add_argument("--demo")
    a = ap.parse_args()
    fams = sorted(FAMILIES) if a.all else a.families
    for fam in fams:
        out = HERE / "instances" / fam
        out.mkdir(parents=True, exist_ok=True)
        if a.demo:
            build_from_demo(fam, a.demo, out)
        f = facts(fam, out)
        (out / "facts.json").write_text(json.dumps(f, indent=1) + "\n")
        print(json.dumps({k: f[k] for k in ("family", "oracle_rows", "instance_sha", "oracle_state_sha", "steps_per_s")}), flush=True)


if __name__ == "__main__":
    main()
