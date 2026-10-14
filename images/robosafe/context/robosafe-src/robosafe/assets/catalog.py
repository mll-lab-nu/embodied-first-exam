"""The catalogue of generated props.

    from robosafe.assets import catalog
    prop = catalog.build("aerosol_can", {"product": "AIR DUSTER", "seed": 3})
    catalog.kinds()                # every kind
    catalog.describe("hot_plate")  # parameters with defaults, tags, zones, controls, looks

A kind is a function `fn(kit, **params)` registered with `@kind(...)` in one of the modules of
`robosafe.assets.kinds`. `build` runs it, writes the MJCF file with its meshes and textures into a per-process cache
directory keyed by a hash of the kind and its parameters, and returns a `robosafe.sim.props.Prop` pointing at it.
Building the same kind with the same parameters gives the same bytes.

Parameters are in metres, kilograms and degrees. `seed` (any kind) draws the parameters listed in the kind's `vary`
table from their ranges; parameters given explicitly win over the draw.
"""
from __future__ import annotations

import atexit
import importlib
import inspect
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from robosafe.core import digest, stream

from .kit import Kit

VERSION = 4                       # part of the cache key: raise it when a builder changes what it makes (3: door buttons; 4: stack light lenses)

_MODULES = ("kitchen", "containers", "electrical", "tools", "figures", "paper", "household", "furniture", "safety",
            "lab", "room")


@dataclass
class KindSpec:
    name: str
    fn: Callable
    priority: int = 1
    fixed: bool = False
    vary: dict = field(default_factory=dict)
    doc: str = ""
    module: str = ""
    # 0.5.1: a fixed paper or light label (a tag or tent card, a sign): a touch of it is listed as an unintended contact
    # but reclasses a hazard trial as `unsafe_capability` only when the thing moved or toppled (`hazard/contact.py`)
    minor_contact: bool = False


_REGISTRY: dict[str, KindSpec] = {}
_LOADED = False


def kind(name: str, *, priority: int = 1, fixed: bool = False, vary: dict | None = None, minor_contact: bool = False):
    """Register a builder. `vary`: parameter -> (low, high) for a number or a list of choices, used by `sample`."""
    def wrap(fn):
        if name in _REGISTRY:
            raise ValueError(f"kind {name!r} registered twice")
        _REGISTRY[name] = KindSpec(name, fn, priority, fixed, dict(vary or {}), (fn.__doc__ or "").strip(), fn.__module__, minor_contact)
        return fn
    return wrap


def _load() -> None:
    global _LOADED
    if _LOADED:
        return
    for m in _MODULES:
        importlib.import_module(f"{__package__}.kinds.{m}")
    _LOADED = True


def kinds(priority: int | None = None) -> list[str]:
    _load()
    return sorted(n for n, s in _REGISTRY.items() if priority is None or s.priority == priority)


def spec(kind: str) -> KindSpec:
    _load()
    if kind not in _REGISTRY:
        raise KeyError(f"unknown catalogue kind {kind!r}; known: {sorted(_REGISTRY)}")
    return _REGISTRY[kind]


def defaults(kind: str) -> dict:
    """The parameters of a kind with their default values."""
    sig = inspect.signature(spec(kind).fn)
    return {n: p.default for n, p in list(sig.parameters.items())[1:]}


def sample(kind: str, seed: int) -> dict:
    """Parameters drawn from the kind's `vary` table: a pure function of the kind and the seed."""
    s = spec(kind)
    rng = stream(int(seed), f"asset:{kind}")
    out = {}
    for name in sorted(s.vary):
        v = s.vary[name]
        if isinstance(v, tuple) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v):
            lo, hi = float(v[0]), float(v[1])
            out[name] = round(lo + (hi - lo) * float(rng.random()), 4)
        else:
            out[name] = v[int(rng.integers(len(v)))]
    return out


def resolve(kind: str, params: dict | None = None) -> dict:
    """The full parameter set a build uses: defaults, then the seeded draw, then what was given."""
    given = dict(params or {})
    seed = given.pop("seed", None)
    full = defaults(kind)
    unknown = sorted(set(given) - set(full))
    if unknown:
        raise TypeError(f"{kind}: unknown parameter(s) {unknown}; it takes {sorted(full)} and seed")
    if seed is not None:
        full.update(sample(kind, int(seed)))
    full.update(given)
    return json.loads(json.dumps(full))        # tuples become lists: one spelling per value


def build_files(kind: str, params: dict | None = None) -> tuple[dict[str, bytes], dict]:
    """Build in memory: `({file name: bytes}, meta)`."""
    s = spec(kind)
    full = resolve(kind, params)
    k = Kit(kind)
    k.fixed = s.fixed
    s.fn(k, **full)
    files, meta = k.finish()
    meta["params"] = full
    files["meta.json"] = (json.dumps(meta, indent=1, sort_keys=True) + "\n").encode("utf8")
    return files, meta


def key(kind: str, params: dict | None = None) -> str:
    return digest({"kind": kind, "params": resolve(kind, params), "version": VERSION})[:16]


def write(kind: str, params: dict | None, out_dir: str | os.PathLike) -> tuple[Path, dict]:
    """Build into `out_dir` (created if need be). Returns the MJCF path and the meta."""
    files, meta = build_files(kind, params)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (out / name).write_bytes(data)
    return out / f"{kind}.xml", meta


_CACHE_DIR: str | None = None
_BUILT: dict[str, tuple[str, dict]] = {}


def cache_dir() -> Path:
    """Where this process keeps what it builds: `$ROBOSAFE_ASSET_CACHE` if set (kept), else a temporary directory
    removed when the process ends."""
    global _CACHE_DIR
    if _CACHE_DIR is None:
        env = os.environ.get("ROBOSAFE_ASSET_CACHE")
        if env:
            Path(env).mkdir(parents=True, exist_ok=True)
            _CACHE_DIR = env
        else:
            _CACHE_DIR = tempfile.mkdtemp(prefix="robosafe_assets_")
            atexit.register(shutil.rmtree, _CACHE_DIR, True)
    return Path(_CACHE_DIR)


def build(kind: str, params: dict | None = None):
    """A catalogue prop: `Prop(kind, path=<MJCF file>, fixed=..., meta=...)`."""
    from robosafe.sim.props import Prop

    k = key(kind, params)
    if k not in _BUILT:
        path, meta = write(kind, params, cache_dir() / f"{kind}-{k}")
        _BUILT[k] = (str(path), meta)
    path, meta = _BUILT[k]
    return Prop(kind, path=path, fixed=bool(meta.get("fixed", False)), meta=json.loads(json.dumps(meta)))


def describe(kind: str) -> dict:
    """What a kind is and takes: parameters with defaults, what `seed` varies, and (from a default build) its tags,
    sites, zones, controls, looks, labels and doors."""
    s = spec(kind)
    _, meta = build_files(kind, None)
    return {"kind": kind, "priority": s.priority, "doc": s.doc, "fixed": s.fixed, "parameters": defaults(kind),
            "vary": {k: list(v) for k, v in s.vary.items()}, "size": meta["size"], "mass": meta["mass"],
            "tags": meta["tags"], "sites": sorted(meta["sites"]), "zones": sorted(meta["zones"]),
            "controls": sorted(meta["controls"]), "looks": sorted(meta["looks"]),
            "labels": [lab["text"] for lab in meta["labels"]], "doors": sorted(meta["doors"]),
            "grasps": [g["name"] for g in meta["grasps"]], "vessel": meta.get("vessel") is not None}
