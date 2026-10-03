"""Versioned, non-pickle relay samples bound to one task and robot scene."""
import json
from pathlib import Path

import numpy as np

from .profiles import normalize_variation


def phase_parts(phase):
    """Strip transit/park suffixes before extracting the abstract hand."""
    return (str(phase).split("/")[0].split(":") + ["", ""])[:3]


def save_samples(path, samples, *, kin, track, holds, identity, plan, assignment, options):
    tcp = {side: [] for side in ("left", "right")}
    stations, sides = [], []
    for sample in samples:
        q = np.asarray(sample["q"], float)
        for side in tcp:
            p, r = kin.tcp_pose(q, side)
            tcp[side].append(np.r_[p, r.as_quat()[[3, 0, 1, 2]], q[kin.robot._q_indices[side][6]]])
        kind, hand, ring = phase_parts(sample["phase"])
        sides.append(assignment.get(hand, ""))
        candidates = [h for h in holds if h["hand"] == hand and h["ring"] == ring
                      and h["sigma_start"]-1e-9 <= sample["sigma"] <= h["sigma_end"]+1e-9]
        hold = max(candidates, key=lambda h: h["sigma_start"], default=None)
        stations.append(np.r_[track.rope([hold["station_m"]], sample["sigma"])[0], hold["station_m"]]
                        if hold and kind in ("transit", "approach", "pinch", "hold") else np.full(4, np.nan))
    metadata = dict(schema_version=1, identity=identity, plan=plan, assignment=assignment, options=options,
                    home_qpos=kin.home.tolist(), robot_ik_verified=True, robot_execution_verified=False,
                    task_success=False, scope="sampled IK and collision checks; no physical execution")
    from topogym.utils.io import to_jsonable
    np.savez_compressed(path, sigma=np.array([s["sigma"] for s in samples]),
                        qpos=np.array([s["q"] for s in samples]), phase=np.array([s["phase"] for s in samples]),
                        side=np.array(sides), tcp_left=np.array(tcp["left"]), tcp_right=np.array(tcp["right"]),
                        station=np.array(stations), metadata_json=json.dumps(to_jsonable(metadata), allow_nan=False))
    load_plan(path)  # Validate the serialization contract before advertising it.


def load_plan(path, *, variant=None, seed=None):
    with np.load(path, allow_pickle=False) as data:
        if "metadata_json" not in data:
            raise ValueError("Samples have no task identity; regenerate with plan_rope_threading_ik.py")
        meta = json.loads(str(data["metadata_json"].item()))
        if meta.get("schema_version") != 1 or meta.get("robot_ik_verified") is not True:
            raise ValueError("Expected a verified IK artifact with schema_version=1")
        identity = meta["identity"]
        if identity["task_id"] != "rope_threading":
            raise ValueError("Samples belong to another task")
        tier = normalize_variation(identity["variation_id"])
        if variant is not None and normalize_variation(variant) != tier:
            raise ValueError("Samples variation differs from requested variant")
        if seed is not None and int(seed) != identity["seed"]:
            raise ValueError("Samples seed differs from requested seed")
        if set(meta["assignment"]) != {"A", "B"} or set(meta["assignment"].values()) != {"left", "right"}:
            raise ValueError("A and B must map to distinct arms")
        arrays = {key: np.array(data[key]) for key in ("sigma", "phase", "side", "qpos", "tcp_left", "tcp_right", "station")}
    n = len(arrays["sigma"])
    if not n or any(len(a) != n for a in arrays.values()):
        raise ValueError("Relay arrays must have the same nonzero sample count")
    for name, shape in (("sigma", (n,)), ("phase", (n,)), ("side", (n,)), ("qpos", (n, 16)),
                        ("tcp_left", (n, 8)), ("tcp_right", (n, 8)), ("station", (n, 4))):
        if arrays[name].shape != shape:
            raise ValueError(f"Invalid {name} shape: {arrays[name].shape}")
    for key in ("sigma", "qpos", "tcp_left", "tcp_right"):
        if not np.isfinite(arrays[key]).all():
            raise ValueError(f"Non-finite {key}")
    if np.any(np.diff(arrays["sigma"]) < -1e-9) or arrays["sigma"][0] < 0:
        raise ValueError("Relay travel must be nonnegative and monotone")
    for side in ("left", "right"):
        tcp = arrays["tcp_"+side]
        if not np.allclose(np.linalg.norm(tcp[:, 3:7], axis=1), 1., atol=1e-6):
            raise ValueError("TCP quaternions must be normalized")
        if np.any(tcp[:, 7] < 0) or np.any(tcp[:, 7] > .037):
            raise ValueError("Invalid ALOHA gripper opening")
    rows = []
    for i in range(n):
        kind, hand, _ = phase_parts(arrays["phase"][i])
        if kind not in {"transit", "approach", "pinch", "hold", "retreat", "park"}:
            raise ValueError(f"Unknown relay phase: {arrays['phase'][i]}")
        if hand not in meta["assignment"] or arrays["side"][i] != meta["assignment"][hand]:
            raise ValueError("Relay phase/side mismatch")
        station = arrays["station"][i]
        if kind in {"transit", "approach", "pinch", "hold"}:
            if not np.isfinite(station).all() or not 0 <= station[3] <= identity["rope_length_m"]:
                raise ValueError("Grasp phase requires a finite rope material station")
        elif not (np.isfinite(station).all() or np.isnan(station).all()):
            raise ValueError("Station must be finite or wholly absent")
        rows.append({key: value[i] for key, value in arrays.items()})
    return rows, meta


def validate_scene(meta, *, task, scene, home_qpos, asset_dir):
    """Reject stale tasks, robot mounts/home or generated assets before actions."""
    import hashlib
    from .geometry import robot_scene_identity
    from topogym.utils.io import to_jsonable
    identity = meta["identity"]
    for key in ("task_id", "variation_id", "model_revision", "terminal_revision", "instance_id"):
        if identity[key] != getattr(task, key):
            raise ValueError(f"Relay {key} differs from current task")
    if to_jsonable(identity["robot_scene"]) != to_jsonable(robot_scene_identity(scene)):
        raise ValueError("Relay robot scene differs from current mount/home/assets")
    if np.shape(home_qpos) != (16,) or not np.allclose(home_qpos, meta["home_qpos"], atol=1e-9):
        raise ValueError("Relay execution must start at the planned default home")
    for name, expected in identity["asset_sha256"].items():
        path = Path(asset_dir)/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Relay task asset differs: {name}")
