"""robomimic-style HDF5 recorder plus a JSON sidecar.

File layout of ``<out>/<task>.hdf5``::

    data/                      attrs: total, env_args (JSON)
      demo_0/                  attrs: num_samples, seed, success
        actions      (T, 16) f32
        phase        (T,)    i32
        obs/<key>    (T, ...)      policy observation, gzip
        privileged/<key> (T, ...)  privileged observation, gzip (optional)
        initial_state          JSON string (or raw bytes)
        states/<key> (T, ...)  optional per-step state arrays

``<out>/<task>.json`` holds ``env_info`` and one entry per episode
(``episode_id, seed, elapsed_steps, success, source_type``).
"""

from __future__ import annotations

import json
import os
import pickle
from typing import Any, Dict, List, Optional

import numpy as np

from .types import EpisodeMeta, ObsDict, RECORD_STRIDE

try:  # h5py is a hard dependency of the recorder but not of the core package
    import h5py
except ImportError:  # pragma: no cover
    h5py = None


def _require_h5py():
    if h5py is None:
        raise ImportError("h5py is required by tactilelab_tasks.core.recorder")


def _encode_state(state: Any) -> np.ndarray:
    """JSON when possible, else pickle; stored as a uint8 array with a ``codec`` attr."""
    try:
        payload = json.dumps(state, default=_json_default).encode("utf-8")
        codec = "json"
    except (TypeError, ValueError):
        payload = pickle.dumps(state)
        codec = "pickle"
    return np.frombuffer(payload, dtype=np.uint8), codec


def _json_default(o):
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.floating, np.integer, np.bool_)):
        return o.item()
    raise TypeError(f"not JSON serialisable: {type(o)}")


def _decode_state(ds) -> Any:
    codec = ds.attrs.get("codec", "json")
    raw = bytes(np.asarray(ds[()], dtype=np.uint8))
    if codec == "pickle":
        return pickle.loads(raw)
    return json.loads(raw.decode("utf-8"))


class Recorder:
    """Write episodes as they are collected.

    Args:
        path: output ``.hdf5`` path; the sidecar is written next to it with ``.json``.
        env_name: task name stored in ``env_args``.
        env_info: extra JSON (sim versions, control mode ...).
        stride: keep every ``stride``-th call to :meth:`record` (default 2 -> 30 Hz).
        compress: gzip level for observation arrays (0 disables).
        policy_keys / privileged_keys: optional whitelists of observation keys.
    """

    def __init__(
        self,
        path: str,
        env_name: str,
        env_info: Optional[dict] = None,
        stride: int = RECORD_STRIDE,
        compress: int = 4,
        policy_keys: Optional[List[str]] = None,
        privileged_keys: Optional[List[str]] = None,
        overwrite: bool = True,
    ):
        _require_h5py()
        self.path = path
        self.json_path = os.path.splitext(path)[0] + ".json"
        self.env_name = env_name
        self.env_info = dict(env_info or {})
        self.stride = max(1, int(stride))
        self.compress = int(compress)
        self.policy_keys = policy_keys
        self.privileged_keys = privileged_keys
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        mode = "w" if overwrite or not os.path.exists(path) else "a"
        self._f = h5py.File(path, mode)
        self._data = self._f.require_group("data")
        self.episodes: List[EpisodeMeta] = []
        if mode == "a" and os.path.exists(self.json_path):
            with open(self.json_path) as fh:
                for e in json.load(fh).get("episodes", []):
                    self.episodes.append(
                        EpisodeMeta(
                            e["episode_id"],
                            e["seed"],
                            e["elapsed_steps"],
                            e["success"],
                            e.get("source_type", "scripted"),
                        )
                    )
        self._ep: Optional[dict] = None
        self._write_root_attrs()

    # ------------------------------------------------------------------ episode API
    @property
    def num_episodes(self) -> int:
        return len(self.episodes)

    def start_episode(self, seed: int, initial_state: Any = None) -> None:
        if self._ep is not None:
            raise RuntimeError("previous episode not finished")
        self._ep = {
            "seed": int(seed),
            "initial_state": initial_state,
            "actions": [],
            "phase": [],
            "obs": {},
            "priv": {},
            "states": {},
            "tick": 0,
            "elapsed": 0,
        }

    def record(
        self, obs: ObsDict, action: np.ndarray, phase: int, state: Optional[Dict[str, np.ndarray]] = None
    ) -> bool:
        """Append one control tick. Returns True if the tick was kept (stride)."""
        ep = self._ep
        if ep is None:
            raise RuntimeError("start_episode first")
        ep["elapsed"] += 1
        keep = (ep["tick"] % self.stride) == 0
        ep["tick"] += 1
        if not keep:
            return False
        ep["actions"].append(np.asarray(action, dtype=np.float32).reshape(-1))
        ep["phase"].append(int(phase))
        for k, v in obs.get("policy", {}).items():
            if self.policy_keys is None or k in self.policy_keys:
                ep["obs"].setdefault(k, []).append(np.asarray(v))
        for k, v in obs.get("privileged", {}).items():
            if self.privileged_keys is None or k in self.privileged_keys:
                ep["priv"].setdefault(k, []).append(np.asarray(v))
        if state:
            for k, v in state.items():
                ep["states"].setdefault(k, []).append(np.asarray(v))
        return True

    def end_episode(self, success: bool, extra: Optional[dict] = None) -> EpisodeMeta:
        ep = self._ep
        if ep is None:
            raise RuntimeError("no episode in progress")
        idx = len(self.episodes)
        g = self._data.create_group(f"demo_{idx}")
        T = len(ep["actions"])
        g.attrs["num_samples"] = T
        g.attrs["seed"] = ep["seed"]
        g.attrs["success"] = bool(success)
        g.attrs["elapsed_steps"] = int(ep["elapsed"])
        g.attrs["stride"] = self.stride
        g.create_dataset("actions", data=np.stack(ep["actions"]) if T else np.zeros((0, 16), np.float32))
        g.create_dataset("phase", data=np.asarray(ep["phase"], dtype=np.int32))
        self._write_group(g.create_group("obs"), ep["obs"])
        if ep["priv"]:
            self._write_group(g.create_group("privileged"), ep["priv"])
        if ep["states"]:
            self._write_group(g.create_group("states"), ep["states"], compress=False)
        if ep["initial_state"] is not None:
            payload, codec = _encode_state(ep["initial_state"])
            ds = g.create_dataset("initial_state", data=payload)
            ds.attrs["codec"] = codec
        meta = EpisodeMeta(idx, ep["seed"], int(ep["elapsed"]), bool(success), "scripted", dict(extra or {}))
        self.episodes.append(meta)
        self._ep = None
        self._write_root_attrs()
        self._f.flush()
        self._write_sidecar()
        return meta

    def discard_episode(self) -> None:
        self._ep = None

    def close(self) -> None:
        if self._f is not None:
            self._write_root_attrs()
            self._f.close()
            self._f = None
            self._write_sidecar()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ------------------------------------------------------------------ internals
    def _write_group(self, grp, arrays: Dict[str, list], compress: Optional[bool] = None) -> None:
        for k, seq in arrays.items():
            arr = np.stack(seq)
            kw = {}
            use = self.compress > 0 if compress is None else compress
            if use and arr.size > 0:
                kw = {"compression": "gzip", "compression_opts": self.compress, "chunks": (1,) + arr.shape[1:]}
            grp.create_dataset(k, data=arr, **kw)

    def env_args(self) -> dict:
        d = {"env_name": self.env_name, "type": 2, "control_mode": "ee_pose_60hz_stride%d" % self.stride}
        d.update(self.env_info)
        return d

    def _write_root_attrs(self) -> None:
        if self._f is None:
            return
        self._data.attrs["total"] = int(sum(int(self._data[k].attrs["num_samples"]) for k in self._data.keys()))
        self._data.attrs["env_args"] = json.dumps(self.env_args(), default=_json_default)

    def _write_sidecar(self) -> None:
        doc = {"env_info": self.env_args(), "episodes": [e.to_json() for e in self.episodes]}
        tmp = self.json_path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(doc, fh, indent=1, default=_json_default)
        os.replace(tmp, self.json_path)


def _read_group(grp) -> Dict[str, np.ndarray]:
    """Flatten a (possibly nested) HDF5 group into ``{"a/b": array}``."""
    out: Dict[str, np.ndarray] = {}

    def visit(name, obj):
        if isinstance(obj, h5py.Dataset):
            out[name] = obj[()]

    grp.visititems(visit)
    return out


def read_dataset(path: str, load_obs: bool = True) -> dict:
    """Read a recorded file back into plain Python/numpy (used by tests and replay).

    Returns ``{"env_args": dict, "total": int, "episodes": [ {name, seed, success,
    num_samples, actions, phase, obs{...}, privileged{...}, states{...}, initial_state} ]}``.
    """
    _require_h5py()
    out = {"episodes": []}
    with h5py.File(path, "r") as f:
        data = f["data"]
        out["total"] = int(data.attrs["total"])
        out["env_args"] = json.loads(data.attrs["env_args"])
        names = sorted(data.keys(), key=lambda s: int(s.split("_")[-1]))
        for name in names:
            g = data[name]
            ep = {
                "name": name,
                "seed": int(g.attrs["seed"]),
                "success": bool(g.attrs["success"]),
                "num_samples": int(g.attrs["num_samples"]),
                "actions": g["actions"][()],
                "phase": g["phase"][()],
                "obs": {},
                "privileged": {},
                "states": {},
                "initial_state": None,
            }
            if load_obs:
                for grp in ("obs", "privileged", "states"):
                    if grp in g:
                        ep[grp] = _read_group(g[grp])
            if "initial_state" in g:
                ep["initial_state"] = _decode_state(g["initial_state"])
            out["episodes"].append(ep)
    sidecar = os.path.splitext(path)[0] + ".json"
    if os.path.exists(sidecar):
        with open(sidecar) as fh:
            out["sidecar"] = json.load(fh)
    return out


__all__ = ["Recorder", "read_dataset", "EpisodeMeta"]
