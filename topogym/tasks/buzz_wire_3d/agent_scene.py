"""Pinned static assets for an episode, with no reference pose or action guide."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import numpy as np

ASSETS = Path(__file__).resolve().parents[3]/"assets/tasks/buzz_wire_3d/compact_single_arm_v1/agent_episode"
SEED_SHA256 = "77ce634e2c2c6aaf57bc094997aaa64598e08e855d39964e192903e4d3de3d5c"


def load_seed():
    raw = (ASSETS/"initial_state.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != SEED_SHA256:
        raise ValueError("Buzz Wire static initialization checksum mismatch")
    seed = json.loads(raw)
    for name, digest in seed["asset_sha256"].items():
        if hashlib.sha256((ASSETS/name).read_bytes()).hexdigest() != digest:
            raise ValueError("Buzz Wire collision asset checksum mismatch: "+name)
    return seed


@dataclass
class StaticWire:
    layout: SimpleNamespace
    rail: np.ndarray
    initial_position: np.ndarray
    initial_quaternion: np.ndarray
    geometry_report: dict


def prepare_scene(folder):
    seed = load_seed()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for name in seed["asset_sha256"]:
        shutil.copy2(ASSETS/name, folder/name)
    shutil.copy2(ASSETS/"initial_state.json", folder/"initial_state.json")
    return StaticWire(SimpleNamespace(**seed["geometry"]), np.asarray(seed["rail_local_m"]),
        np.asarray(seed["initial_wand_local"]["position_m"]),
        np.asarray(seed["initial_wand_local"]["quaternion_wxyz"]), seed["geometry_report"])
