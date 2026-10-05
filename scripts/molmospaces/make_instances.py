#!/usr/bin/env python3
"""Freeze the MolmoSpaces instances: for every family of families.json, take three candidates from its upstream package
by the rule in docs/benchmarks/molmospaces.md (Instances) and write the one whose upstream episode index families.json
`keep`s to scripts/molmospaces/instances/<family>-i00.json. All three are found, so that the kept episode provably is one
of the rule's candidates.

    python scripts/molmospaces/make_instances.py --bench <molmospaces-bench-v2/20260415 dir> [family ...]
    python scripts/molmospaces/make_instances.py --bench <dir> --refresh [family ...]   # recompute facts / t = 0 only
    python scripts/molmospaces/make_instances.py --bench <dir> --candidates <dir> family  # also write all three

Needs the simulator (molmo-spaces 0.2.9, MuJoCo 3.5.0, MLSPACES_ASSETS_DIR / MLSPACES_CACHE_DIR set, and
MLSPACES_PINNED_ASSETS_FILE=images/molmospaces/pinned_assets.json, the Objaverse version the benchmark was made with)
and the network: upstream installs the assets an episode uses on first load, and the houses of the public MolmoBot
trajectories are read from Hugging Face. An instance is the upstream episode unchanged except: `source` (the path of the
episode's own expert trajectory) is dropped, and the navigation text, wrong in this package ("pick up the black
television."), is upstream NavToObjTask's own description."""

import argparse
import json
import math
import re
import sys
import urllib.request
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
import rcb_molmospaces as M  # noqa: E402

BENCHMARK = "molmospaces-bench-v2/20260415"
CLUTTER_M, CLUTTER_N = 0.3, 3  # pick families: other objects whose pose lies within 30 cm of the target's
NAV_MIN_M = 5.0  # navigation: the nearest target's distance from the robot base at t = 0
MOLMOBOT = "https://huggingface.co/datasets/allenai/molmobot-data"
MOLMOBOT_CONFIGS = (
    "DoorOpeningDataGenConfig",
    "FrankaPickAndPlaceColorOmniCamConfig",
    "FrankaPickAndPlaceNextToOmniCamConfig",
    "FrankaPickAndPlaceOmniCamConfig",
    "FrankaPickOmniCamConfig",
    "RBY1OpenDataGenConfig",
    "RBY1PickAndPlaceDataGenConfig",
    "RBY1PickDataGenConfig",
)


def public_trajectory_houses() -> set[int]:
    houses = set()
    for cfg in MOLMOBOT_CONFIGS:
        table = json.load(urllib.request.urlopen(f"{MOLMOBOT}/resolve/main/{cfg}/val_arrow_table.json"))
        houses |= {int(m.group(1)) for row in table for m in [re.search(r"_house_(\d+)\.", row["path"])] if m}
    return houses


def joint_kind(ep: M.Episode) -> str:
    import mujoco

    m = ep.env.current_model
    j = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, ep.inst["episode"]["task"]["joint_name"])
    return "slide" if int(m.jnt_type[j]) == int(mujoco.mjtJoint.mjJNT_SLIDE) else "hinge"


def variant(family: str, episode: dict) -> str:
    """The variant an episode shows, from its upstream fields (no simulator needed)."""
    t, lang = episode["task"], episode["language"]
    if family.startswith("pick"):
        return "b" if t["pickup_obj_name"].startswith("obja") else "a"  # Objaverse : AI2-THOR object
    if family in ("open", "close"):
        return "a" if lang["referral_expressions"]["pickup_obj_name"] == "drawer" else "b"
    if family == "navigate-to":
        return "a" if len(t.get("pickup_obj_candidates") or [None]) == 1 else "b"
    if family == "open-door":
        return "a" if lang["task_description"].startswith("Push") else "b"
    raise KeyError(family)


def ruled_out(family: str, episode: dict) -> str | None:
    """Why an episode is not used, from its upstream fields alone (no simulator): an ambiguous target, or not hard
    enough. None if it may be."""
    t, poses = episode["task"], episode["scene_modifications"].get("object_poses", {})
    if family.startswith("pick"):
        copies = [
            n
            for n in poses
            for m in (t["pickup_obj_name"], t.get("place_receptacle_name"))
            if m and n != m and same_asset(n, m)
        ]
        if copies:
            return f"identical copies of the target or receptacle: {', '.join(copies)}"
        o, skip = t["pickup_obj_start_pose"], {t["pickup_obj_name"], t.get("place_receptacle_name")}
        n = sum(1 for name, p in poses.items() if name not in skip and math.dist(p[:3], o[:3]) < CLUTTER_M)
        return f"{n} other objects within {CLUTTER_M:g} m of the target" if n < CLUTTER_N else None
    if family == "navigate-to":
        cands = t.get("pickup_obj_candidates") or [t["pickup_obj_name"]]
        if all(c in poses for c in cands):  # otherwise the simulator measures it (checked)
            d = min(math.dist(t["robot_base_pose"][:2], poses[c][:2]) for c in cands)
            return f"the nearest target is {d:.2f} m away" if d < NAV_MIN_M else None
    return None


def same_asset(a: str, b: str) -> bool:
    """Two scene objects made from one asset: their names differ only in the instance suffix (`<asset>_<k>_0_<n>`)."""
    return re.sub(r"_\d+_\d+_\d+$", "", a) == re.sub(r"_\d+_\d+_\d+$", "", b)


def checked(family: str, hit: str, ep: M.Episode) -> str | None:
    """Why a built episode is not used, or None."""
    gone = missing_objects(ep)
    if gone:
        return "objects missing: " + ", ".join(gone)
    restricted = noncommercial_objects(ep)
    if restricted:
        return "non-commercial assets: " + ", ".join(restricted)
    if ep.success():
        return "already successful at t = 0"
    kind = joint_kind(ep) if family in ("open", "close") else None
    if kind and kind != ("slide" if hit == "a" else "hinge"):
        return f"the target joint is a {kind} joint"
    if family == "navigate-to":
        return nav_targets(hit, ep) or nav_far(ep)
    return None


def nav_far(ep: M.Episode) -> str | None:
    """Why the nearest target is not far and out of view at t = 0 (upstream's own checks), or None."""
    d, seen = ep.task.calculate_distance(0), ep.task.check_object_visible(0)
    if d < NAV_MIN_M or seen:
        return f"the nearest target is {d:.2f} m away" + (" and in view" if seen else "")
    return None


def nav_targets(hit: str, ep: M.Episode) -> str | None:
    """Why a navigation episode's targets are not the kind of object its text names, or None. Upstream keeps the
    candidates of the target's category (category_from_name), and an Objaverse object's category is its library
    ("obja"): every Objaverse object in the house would stay a target. Every candidate must have the target's WordNet
    synset, and variant b must keep several."""
    cfg = ep.task.config.task_config
    om = ep.env.object_managers[ep.env.current_batch_index]
    want, cands = (
        om.get_annotation_synset(cfg.pickup_obj_name),
        list(cfg.pickup_obj_candidates or [cfg.pickup_obj_name]),
    )
    other = [c for c in cands if om.get_annotation_synset(c) != want]
    if other:
        return f"{len(other)} of {len(cands)} candidate targets are not a {want}"
    return "one candidate target left" if hit == "b" and len(cands) < 2 else None


def facts(family: str, ep: M.Episode) -> dict:
    """The numbers the instruction quotes, from the episode's task config (as upstream reads them)."""
    t, cfg = ep.inst["episode"]["task"], ep.task.config.task_config
    out = {
        "goal": ep.task.get_task_description(),
        "horizon_steps": ep.horizon,
        "horizon_s": t["task_horizon_sec"],
        "control_hz": round(1.0 / ep.dt, 3),
    }
    if family == "pick":
        out["lift_cm"] = round(100 * t["succ_pos_threshold"], 3)
    elif family in ("pick-and-place", "pick-and-place-color", "pick-and-place-next-to"):
        out |= {
            "support_pct": round(100 * cfg.receptacle_supported_weight_frac, 3),
            "carry_mm": round(1000 * cfg.carry_forward_rel_pos_threshold, 3),
            "carry_deg": round(float(np.degrees(cfg.carry_forward_rel_rot_threshold)), 3),
            "max_disp_cm": round(100 * cfg.max_place_receptacle_pos_displacement, 3),
            "max_tilt_deg": round(float(np.degrees(cfg.max_place_receptacle_rot_displacement)), 3),
        }
        if family == "pick-and-place-next-to":
            from molmo_spaces.tasks.pick_and_place_next_to_task import _get_surface_gap

            out |= {
                "min_gap_cm": round(100 * _get_surface_gap(ep.task.config, "min_surface_to_surface_gap", 0.0), 3),
                "max_gap_cm": round(
                    100 * (_get_surface_gap(ep.task.config, "max_surface_to_surface_gap", 0.05) + 0.01), 3
                ),
                "max_rot_deg": out.pop("max_tilt_deg"),
            }
    elif family == "open":
        target = ep.inst["episode"]["language"]["referral_expressions"]["pickup_obj_name"]
        out |= {
            "open_pct": round(100 * t["task_success_threshold"], 3),
            "scope": f"any {target} in the room" if t.get("any_inst_of_category") else f"the {target}",
        }
    elif family == "close":
        lo, hi = ep.task.articulation_objects[0][0].get_joint_range(t["joint_index"])
        out |= {
            "close_pct": round(100 * (1 - t["task_success_threshold"]), 3),
            "start_pct": 100 * abs(t["joint_start_position"][0]) / abs(hi - lo),
        }
    elif family == "navigate-to":
        n = len(t.get("pickup_obj_candidates") or [1])
        out |= {
            "near_m": t["succ_pos_threshold"],
            "candidates": "target object" if n == 1 else f"one of the {n} target objects",
        }
    elif family == "open-door":
        lo, hi = t["articulated_joint_range"]
        out |= {
            "open_pct": round(100 * t["door_openness_threshold"], 3),
            "range_deg": round(float(np.degrees(hi - lo)), 1),
        }
    return out


def candidate(family: str, fam: dict, idx: int, episode: dict) -> dict:
    episode = json.loads(json.dumps(episode))
    episode.pop("source", None)
    return {
        "benchmark": "molmospaces",
        "family": family,
        "upstream": {
            "benchmark": BENCHMARK,
            "package": fam["package"],
            "episode_index": idx,
            "name": fam["upstream_benchmark"],
        },
        "robot_config": fam["robot_config"],
        "policy_dt_ms": fam["policy_dt_ms"],
        "agent_cameras": [c["name"] for c in episode["cameras"] if c["name"] != "camera_follower"],
        "episode": episode,
    }


def noncommercial_objects(ep: M.Episode) -> list[str]:
    """The episode's Objaverse objects whose licence forbids commercial use (CC BY-NC / BY-NC-SA in upstream's own
    per-object record): the image redistributes every asset an episode loads, and stays publishable without them. Every
    Objaverse object the episode loads names its asset id in its MuJoCo body or mesh name."""
    from molmo_spaces.utils.object_metadata import ObjectMeta

    m = ep.env.current_model
    names = [m.body(b).name for b in range(m.nbody)] + [m.mesh(i).name for i in range(m.nmesh)]
    out = []
    for uid in sorted({u for n in names for u in re.findall(r"[0-9a-f]{32}", n)}):
        meta = ObjectMeta.annotation(uid) or {}
        lic = (meta.get("license_info") or {}).get("license", "")
        if meta.get("isObjaverse") and "nc" in lic.split("-"):
            out.append(f"{meta.get('category')} {uid} ({lic})")
    return out


def missing_objects(ep: M.Episode) -> list[str]:
    import mujoco

    m = ep.env.current_model
    names = ep.inst["episode"]["scene_modifications"]["object_poses"]
    return [n for n in names if mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, n) < 0]


def record(inst: dict, ep: M.Episode) -> dict:
    """The facts the instance's texts quote and its t = 0 record."""
    return {
        "facts": facts(inst["family"], ep),
        "t0": {
            "state_sha": ep.state_sha(),
            "horizon_steps": ep.horizon,
            "action_dim": ep.action_dim,
            "layout": ep.layout,
            "tcp_frames": ep.grippers,
            "joint_names": ep.joint_names,
            "targets": [float(v) for v in ep.hold_row()],  # the controllers' targets at t = 0
        },
    }


def write(inst: dict, path: Path) -> None:
    path.write_text(json.dumps(inst, indent=1) + "\n")


def refresh(path: Path) -> None:
    """Rebuild a frozen instance and rewrite its facts and t = 0 record (the episode stays as frozen)."""
    inst = M.load_instance(path)
    M.install(inst)
    ep = M.Episode(inst)
    try:
        inst |= record(inst, ep)
        write(inst, path)
        print(f"{path.name}: refreshed ({inst['t0']['state_sha']})", flush=True)
    finally:
        ep.close()


def select(family: str, fam: dict, bench: Path, excluded: set[int], out_dir: Path, cand_dir: Path | None) -> None:
    episodes = json.loads((bench / fam["package"] / "benchmark.json").read_text())
    kept = []  # (variant, instance, its record) of the episodes that pass, in package order
    for idx, episode in enumerate(episodes):
        count = {v: sum(1 for h, *_ in kept if h == v) for v in fam["variants"]}
        if all(count.values()) and len(kept) >= 3:
            break
        hit = variant(family, episode)
        if count[hit] >= 2 or episode["house_index"] in excluded:  # a third of one variant is never used
            continue
        if episode["house_index"] in {i["episode"]["house_index"] for _, i, _ in kept}:  # one instance per house
            continue
        if ruled_out(family, episode):
            continue
        inst = candidate(family, fam, idx, episode)
        try:
            M.install(inst)
            ep = M.Episode(inst)
        except Exception as exc:  # noqa: BLE001 -- an episode upstream cannot build is skipped
            print(f"{family} #{idx}: upstream could not build it ({exc!r:.160})", flush=True)
            continue
        try:
            why = checked(family, hit, ep)
            if why:
                print(f"{family} #{idx}: skipped ({why})", flush=True)
                continue
            if family == "navigate-to":
                from molmo_spaces.tasks.nav_task import NavToObjTask

                inst["episode"]["language"]["task_description"] = NavToObjTask.get_task_description(ep.task)
                ep.task.get_task_description = lambda: inst["episode"]["language"]["task_description"]
            kept.append((hit, inst, record(inst, ep)))
            print(f"{family} #{idx}: passes ({fam['variants'][hit]}): {kept[-1][2]['facts']['goal']}", flush=True)
        finally:
            ep.close()
    first = {v: next((k for k, (h, *_) in enumerate(kept) if h == v), None) for v in fam["variants"]}
    if None in first.values() or len(kept) < 3:
        raise SystemExit(f"{family}: {len(kept)} episodes pass ({[h for h, *_ in kept]}); need both variants and three")
    rest = next(k for k in range(len(kept)) if k not in first.values())
    candidates = [kept[k] for k in (*first.values(), rest)]
    print(f"{family}: candidates {[inst['upstream']['episode_index'] for _, inst, _ in candidates]}", flush=True)
    if cand_dir:  # the runs that choose `keep` need all three
        cand_dir.mkdir(parents=True, exist_ok=True)
        for hit, inst, rec in candidates:
            idx = inst["upstream"]["episode_index"]
            write(inst | {"instance": "i00", "variant": fam["variants"][hit]} | rec, cand_dir / f"{family}-{idx}.json")
    chosen = [c for c in candidates if c[1]["upstream"]["episode_index"] == fam["keep"]]
    if not chosen:
        if cand_dir:  # choosing `keep` from the candidates just written
            return
        raise SystemExit(f"{family}: the kept episode {fam['keep']} is not one of the candidates")
    hit, inst, rec = chosen[0]
    inst = inst | {"instance": "i00", "variant": fam["variants"][hit]} | rec
    write(inst, out_dir / f"{family}-i00.json")
    print(f"{family} #{fam['keep']}: kept ({inst['variant']}) -> {family}-i00.json", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bench", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=HERE / "instances")
    ap.add_argument(
        "--refresh", action="store_true", help="rewrite the facts and t = 0 record of the existing instances"
    )
    ap.add_argument("--candidates", type=Path, help="also write the three candidates to this directory")
    ap.add_argument("families", nargs="*")
    a = ap.parse_args()
    fams = json.loads((HERE / "families.json").read_text())["families"]
    M.boot(install=True)
    if a.refresh:
        for path in sorted(a.out.glob("*.json")):
            if not a.families or M.load_instance(path)["family"] in a.families:
                refresh(path)
        return 0
    excluded = public_trajectory_houses()
    a.out.mkdir(parents=True, exist_ok=True)
    for family in a.families or fams:
        select(family, fams[family], a.bench, excluded, a.out, a.candidates)
    return 0


if __name__ == "__main__":
    sys.exit(main())
