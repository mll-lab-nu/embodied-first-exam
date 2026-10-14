"""Hand selection shared by every DexHand family (artifacts HAND_INTERFACE.md is the contract).

Two genuine manufacturer models are supported:

* ``sharpa``: Sharpa Wave (MuJoCo Menagerie ``sharpa_wave``), 22 finger actuators. Default.
* ``wuji``: Wuji Hand 2.2 (``wuji-technology/wuji-description`` ``hand2/hand2_2``), 20 finger actuators.

The hand is chosen by ``Session(..., hand=...)`` or, when that argument is omitted, by the ``DEXHAND_HAND``
environment variable; graders never read the variable and take the hand from the trusted record instead
(the trajectory archive in privileged mode, the service's episode record in standard mode).
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

import numpy as np

ENV_VAR = "DEXHAND_HAND"
DEFAULT_HAND = "sharpa"
HANDS = {
    "sharpa": {
        "id": "sharpa",
        "model": "Sharpa Wave",
        "robot": "sharpa-wave",
        "finger_actuators": 22,
        "source": "google-deepmind/mujoco_menagerie sharpa_wave @ 0059d4335f8156206f63a35662313385f7ad6d74",
        "license": "Apache-2.0",
    },
    "wuji": {
        "id": "wuji",
        "model": "Wuji Hand 2.2",
        "robot": "wuji-hand-2.2",
        "finger_actuators": 20,
        "source": "wuji-technology/wuji-description hand2/hand2_2 @ 829c9aa27cb12c3a49d5b8d63c9869dd8f656702",
        "license": "MIT",
    },
}
ALIASES = {"sharpa_wave": "sharpa", "sharpa-wave": "sharpa", "wave": "sharpa",
           "wuji_v2_2": "wuji", "wuji-hand-2.2": "wuji", "hand2_2": "wuji"}
FINGERS = ("thumb", "index", "middle", "ring", "pinky")
# Mounting rotations (Wuji native frame -> Wave native frame), per side, mapping fingers, palm normal and thumb side:
# * right: Wave fingers +Z, palm normal +X, thumb +Y; Wuji (right.xml) fingers -Z, palm normal +Y (positive
#   *_mcp_flex about +X curls toward +Y), thumb/index side +X.  R @ (0,0,-1) = +Z, R @ (0,1,0) = +X, R @ (1,0,0) = +Y.
# * left: the Wave left hand is the right model mirrored in Y (fingers +Z, palm +X, thumb -Y); Wuji left.xml is
#   mirrored in Y too (flex axis -X: palm normal -Y, thumb +X).  R @ (0,0,-1) = +Z, R @ (0,-1,0) = +X, R @ (1,0,0) = -Y.
# scripts/hand_support/profiles.py uses the left matrix for both sides, which mounts a RIGHT Wuji palm-down
# (rotated 180 degrees about the finger axis relative to the Wave it replaces).
WUJI_TO_WAVE = {
    "r": np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, -1.0]]),
    "l": np.array([[0.0, -1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, -1.0]]),
}
WUJI_MOUNT_QUAT = {  # wxyz of WUJI_TO_WAVE[side]
    "r": (0.0, 0.7071067811865476, 0.7071067811865476, 0.0),
    "l": (0.0, 0.7071067811865476, -0.7071067811865476, 0.0),
}
WAVE_ROOTS = {"right_hand_C_MC": "r", "left_hand_C_MC": "l", "r_hand_palm": "r", "l_hand_palm": "l"}


class HandError(ValueError):
    """A hand name, asset or hand-specific trajectory is invalid."""


def canonical(value) -> str:
    """Return ``sharpa`` or ``wuji``; anything else is an error (never a silent fallback)."""
    if not isinstance(value, str):
        raise HandError(f"hand must be a string, got {type(value).__name__}")
    key = value.strip().lower()
    key = ALIASES.get(key, key)
    if key not in HANDS:
        raise HandError(f"Unknown hand {value!r}; choose one of {sorted(HANDS)}")
    return key


def offered() -> tuple[list[str], str]:
    """(the hands this task offers, why not more): ``offered_hands.json`` beside this file, which the generator writes
    into a task's runtime directory when its family offers fewer hands (task.toml ``hands``); else every hand."""
    path = Path(__file__).with_name("offered_hands.json")
    if path.is_file():
        value = json.loads(path.read_text())
        return [canonical(hand) for hand in value["hands"]], str(value.get("reason", ""))
    return list(HANDS), ""


def require_offered(hand: str) -> str:
    """``hand`` if this task offers it; otherwise HandError (Session, the standard service and every replay)."""
    names, reason = offered()
    if hand not in names:
        raise HandError(f"Hand {hand!r} is not offered in this task (only {', '.join(names)})"
                        + (f": {reason}" if reason else ""))
    return hand


def selected(hand=None) -> str:
    """The explicit argument wins; otherwise ``DEXHAND_HAND``; otherwise the default (sharpa). A hand the task does
    not offer (``offered()``) is an error."""
    if hand is not None:
        return require_offered(canonical(hand))
    value = os.environ.get(ENV_VAR, "").strip()
    return require_offered(canonical(value) if value else DEFAULT_HAND)


def info(hand) -> dict:
    return dict(HANDS[canonical(hand)])


# --------------------------------------------------------------------------------------------- assets
def sharpa_dir() -> Path:
    return Path(os.environ.get("DEXHAND_ASSET_DIR", "/opt/dexhand/hand"))


def wuji_dir() -> Path:
    """``WUJI_ASSET_DIR``, else the image path, else a sibling of the Sharpa asset folder (repository checkout)."""
    if os.environ.get("WUJI_ASSET_DIR"):
        return Path(os.environ["WUJI_ASSET_DIR"])
    for candidate in (Path("/opt/dexhand/wuji_v2_2"), sharpa_dir().parent / "wuji_v2_2"):
        if (candidate / "mjcf/right.xml").is_file():
            return candidate
    raise HandError("Wuji Hand 2.2 assets not found (set WUJI_ASSET_DIR or use the eai-dexhand image)")


_VERIFIED: dict[str, dict] = {}


def verify_wuji(folder: Path | None = None) -> dict:
    """Check every present runtime file (MJCF, meshes, license) against the pinned manifest.

    The image ships the MJCF/mesh subset; presentation-only USD files are not needed by physics and may be absent,
    but every MJCF and mesh file the manifest lists must be present and byte-exact.
    """
    folder = Path(folder or wuji_dir())
    key = str(folder.resolve())
    if key in _VERIFIED:
        return _VERIFIED[key]
    manifest = json.loads((folder / "manifest.json").read_text())
    if manifest.get("upstream_model") != "hand2/hand2_2":
        raise HandError("Formal Wuji hand2/hand2_2 assets required")
    for path, expected in manifest["files"].items():
        target = folder / path
        required = path.startswith(("mjcf/", "meshes/")) or path == "LICENSE"
        if not target.is_file():
            if required:
                raise HandError(f"Wuji asset missing: {path}")
            continue
        raw = target.read_bytes()
        if len(raw) != expected["bytes"] or hashlib.sha256(raw).hexdigest() != expected["sha256"]:
            raise HandError(f"Wuji asset integrity failure: {path}")
    _VERIFIED[key] = manifest
    return manifest


# --------------------------------------------------------------------------------------------- composition
def _text(values) -> str:
    return " ".join(f"{float(x):.17g}" for x in values)


def _section(root, tag):
    found = root.find(tag)
    return found if found is not None else ET.SubElement(root, tag)


def merge_wuji(root, parent, side="r", *, pos=(0, 0, 0), quat=(1, 0, 0, 0), folder: Path | None = None) -> dict:
    """Attach the genuine left/right Wuji Hand 2.2 under ``parent`` with scoped names and defaults.

    Same naming as scripts/hand_support/profiles.py: every vendor name gets the prefix ``<side>_wuji_``
    (``r_wuji_r_FFJ0`` ...). Vendor joint/actuator/contact parameters are unchanged.
    """
    side = {"right": "r", "left": "l"}.get(side, side)
    if side not in ("l", "r"):
        raise HandError("Expected l/left or r/right")
    folder = Path(folder or wuji_dir())
    verify_wuji(folder)
    source = folder / f"mjcf/{'left' if side == 'l' else 'right'}.xml"
    hand = ET.parse(source).getroot()
    prefix = side + "_wuji_"
    mapping = {item.get("name"): prefix + item.get("name") for item in hand.iter() if item.get("name")}
    refs = {"name", "class", "childclass", "mesh", "material", "joint", "body1", "body2", "geom1", "geom2", "site"}
    meshdir = source.parent / hand.find("compiler").get("meshdir", "")
    for item in hand.iter():
        for attr in refs & item.attrib.keys():
            if item.get(attr) in mapping:
                item.set(attr, mapping[item.get(attr)])
        if item.tag == "mesh" and item.get("file"):
            item.set("file", str((meshdir / item.get("file")).resolve()))
    defaults = copy.deepcopy(hand.find("default"))
    defaults.set("class", prefix + "defaults")
    _section(root, "default").append(defaults)
    for tag in ("asset", "contact", "actuator", "sensor"):
        vendor = hand.find(tag)
        if vendor is not None:
            _section(root, tag).extend(copy.deepcopy(list(vendor)))
    body = copy.deepcopy(hand.find("worldbody/body"))
    body.set("childclass", prefix + "defaults")
    body.set("pos", _text(pos))
    body.set("quat", _text(quat))
    for link in body.iter("body"):
        for i, item in enumerate(link.findall("geom")):
            item.set("name", link.get("name") + ("_visual" if item.get("contype") == "0" else "_collision") + str(i))
    parent.append(body)
    actuators = hand.find("actuator")
    return dict(
        hand="wuji",
        side=side,
        root_body=body.get("name"),
        prefix=prefix,
        joint_names=[a.get("joint") for a in actuators],
        actuator_names=[a.get("name") for a in actuators],
        fingertip_sites={f: mapping[f"{side}_{f if f in ('thumb', 'pinky') else f + '_finger'}_tip"] for f in FINGERS},
        source=str(source),
        mirrored=False,
    )


def _remove_references(root, removed: set[str]) -> None:
    keys = {"joint", "joint1", "joint2", "body", "body1", "body2", "geom1", "geom2", "site", "site1", "site2", "tendon"}
    for tag in ("actuator", "sensor", "contact", "equality", "tendon"):
        found = root.find(tag)
        if found is not None:
            for item in list(found):
                if any(child.get(key) in removed for child in item.iter() for key in keys):
                    found.remove(item)


def replace_wave_hands(root, hand, *, folder: Path | None = None) -> list[dict]:
    """Swap every Sharpa Wave hand body of an MJCF tree for the selected hand, in place.

    ``sharpa`` leaves the tree unchanged. ``wuji`` removes each Wave root body (``right_hand_C_MC`` ...) and its
    actuators/sensors/contacts, inserts a fixed wrapper body with the same name, position and orientation (cameras
    and frames anchored at the old mount keep working), and mounts the genuine Wuji model in it with the rigid
    per-side WUJI_TO_WAVE rotation (palm, fingers and thumb side aligned with the Wave's). The wrist stage or arm joints above the mount are untouched, so the same mount controls
    drive either hand. Wuji actuators are appended after the remaining (non-hand) actuators.
    """
    hand = canonical(hand)
    wave = [(parent, body, WAVE_ROOTS[body.get("name")])
            for parent in root.iter() for body in parent.findall("body") if body.get("name") in WAVE_ROOTS]
    if not wave:
        raise HandError("No Sharpa Wave hand body in this scene")
    if hand == "sharpa":
        return [dict(hand="sharpa", side=side, root_body=body.get("name")) for _, body, side in wave]
    records = []
    for parent, body, side in wave:
        removed = {item.get("name") for item in body.iter() if item.get("name")}
        _remove_references(root, removed)
        wrapper = ET.Element("body", name=body.get("name"), pos=body.get("pos", "0 0 0"),
                             quat=body.get("quat", "1 0 0 0"))
        parent.insert(list(parent).index(body), wrapper)
        parent.remove(body)
        records.append(merge_wuji(root, wrapper, side, quat=WUJI_MOUNT_QUAT[side], folder=folder))
        for camera in body.findall("camera"):
            wrapper.append(copy.deepcopy(camera))
    for keyframes in root.findall("keyframe"):
        root.remove(keyframes)
    _drop_unreferenced_meshes(root)
    return records


def _drop_unreferenced_meshes(root) -> None:
    """Remove mesh assets no geom uses (the replaced Wave meshes).

    MuJoCo caches decoded meshes per process; an unused mesh asset would make the compiled Wuji model (and any hash of
    it) depend on which scenes were compiled earlier in the same process. Physics never used them.
    """
    used = {item.get("mesh") for item in root.iter() if item.tag in ("geom", "site") and item.get("mesh")}
    used |= {item.get("mesh") for item in root.iter("skin") if item.get("mesh")}
    assets = root.find("asset")
    if assets is None:
        return
    for mesh in list(assets.findall("mesh")):
        if mesh.get("name") not in used:
            assets.remove(mesh)


def finger_of(name: str) -> str | None:
    """Map a hand geom/body/joint name of either model to thumb/index/middle/ring/pinky.

    The finger is the finger word that comes first in the name: link names put the finger before the link, and a
    later word names the phalanx (Wuji ``r_ring_finger_middle`` is the ring finger's middle phalanx, not the middle
    finger; ``r_pinky_middle`` belongs to the pinky).
    """
    lowered = (name or "").lower()
    found = [(lowered.find(finger), finger) for finger in FINGERS if finger in lowered]
    return min(found)[1] if found else None


# --------------------------------------------------------------------------------------------- trajectories
TRAJECTORY_MEMBERS = {"actions.npy", "hand.npy", "task.npy", "actuator_names.npy"}


def _read_member(archive: zipfile.ZipFile, member: zipfile.ZipInfo, *, numeric: bool, max_items: int):
    """Validate a member's NumPy header and payload size, then read it without pickle (never via np.load[key])."""
    with archive.open(member) as stream:
        version = np.lib.format.read_magic(stream)
        if version == (1, 0):
            shape, fortran, dtype = np.lib.format.read_array_header_1_0(stream, max_header_size=10_000)
        elif version == (2, 0):
            shape, fortran, dtype = np.lib.format.read_array_header_2_0(stream, max_header_size=10_000)
        else:
            raise HandError(f"{member.filename}: NumPy format version 1 or 2 required")
        if dtype.hasobject or dtype.kind not in ("fiu" if numeric else "U"):
            raise HandError(f"{member.filename}: {'numeric' if numeric else 'string'} array required")
        count = int(np.prod(shape)) if shape else 1
        if count > max_items or stream.tell() + count * dtype.itemsize != member.file_size:
            raise HandError(f"{member.filename}: header does not match its payload or exceeds the size limit")
    with archive.open(member) as stream:
        return np.lib.format.read_array(stream, allow_pickle=False)


def _single_string(value: np.ndarray, key: str) -> str:
    if value.size != 1:
        raise HandError(f"{key} must hold exactly one string")
    return str(value.reshape(-1)[0])


def read_trajectory(path, *, widths: dict, max_rows: int | None, task: str | None = None,
                    allow_empty: bool = False, max_bytes: int = 64_000_000, max_expanded_bytes: int | None = None):
    """Read ``(actions float64 (T, D), hand, actuator_names or None)``; reject anything ambiguous.

    * ``actions``: numeric, finite, 2-D; required. ``hand``: optional, exactly one string, default ``sharpa``.
    * ``task`` (one string) and ``actuator_names`` (1-D strings) are optional; when present they must match.
    * Members are read by their exact ``<key>.npy`` name with ``allow_pickle=False``. A member that could be confused
      with a recognised key (``actions``, ``hand``, ... without ``.npy``, or duplicated names) is rejected; any other
      member is ignored and never influences the verdict.
    * The width must equal ``widths[hand]`` exactly: no padding, truncation or cross-hand replay.
    """
    path = Path(path)
    if path.stat().st_size > max_bytes:   # the file (tests/grade.py checks the same 64 MB before any replay)
        raise HandError(f"trajectory archive is larger than {max_bytes:,} bytes (save it with numpy.savez_compressed)")
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        expanded = max_bytes if max_expanded_bytes is None else max_expanded_bytes
        if len(entries) > 32 or sum(item.file_size for item in entries) > expanded:
            raise HandError(f"trajectory archive expands to more than {expanded:,} bytes")
        names = [item.filename for item in entries]
        if len(names) != len(set(names)):
            raise HandError("trajectory archive has duplicate member names")
        stems = {name[:-4] for name in TRAJECTORY_MEMBERS}
        for name in names:
            if name not in TRAJECTORY_MEMBERS and (name in stems or name.split("/")[-1].removesuffix(".npy") in stems):
                raise HandError(f"ambiguous trajectory member {name!r}")
        members = {item.filename: item for item in entries}
        if "actions.npy" not in members:
            raise HandError("trajectory must contain an actions.npy member")
        actions = _read_member(archive, members["actions.npy"], numeric=True,
                               max_items=max_bytes // 8)
        hand = (_single_string(_read_member(archive, members["hand.npy"], numeric=False, max_items=1), "hand")
                if "hand.npy" in members else DEFAULT_HAND)
        stored_task = (_single_string(_read_member(archive, members["task.npy"], numeric=False, max_items=1), "task")
                       if "task.npy" in members else None)
        names_value = None
        if "actuator_names.npy" in members:
            value = _read_member(archive, members["actuator_names.npy"], numeric=False, max_items=256)
            if value.ndim != 1:
                raise HandError("actuator_names must be a 1-D string array")
            names_value = [str(x) for x in value]
    hand = require_offered(canonical(hand))
    if task is not None and stored_task is not None and stored_task != task:
        raise HandError(f"trajectory task {stored_task!r} differs from {task!r}")
    if hand not in widths:
        raise HandError(f"hand {hand!r} is not available in this task")
    width = int(widths[hand])
    if actions.ndim != 2 or actions.shape[1] != width:
        raise HandError(f"{hand} actions must have shape (T, {width}); got {tuple(actions.shape)}")
    if (len(actions) == 0 and not allow_empty) or (max_rows is not None and len(actions) > max_rows):
        raise HandError(f"actions must have 1 to {max_rows} rows")
    if not np.isfinite(actions).all():
        raise HandError("actions must contain finite numeric values")
    return np.asarray(actions, dtype=np.float64), hand, names_value


def write_trajectory(path, actions, *, hand, task=None, actuator_names=None) -> None:
    """Write the deliverable: ``actions`` plus the ``hand`` (and optional task / actuator names) as strings."""
    rows = np.asarray(actions, dtype=np.float64)
    if rows.ndim != 2 or not np.isfinite(rows).all():
        raise HandError("actions must be a finite (T, D) array")
    extra = {"hand": np.array(canonical(hand))}
    if task is not None:
        extra["task"] = np.array(str(task))
    if actuator_names is not None:
        extra["actuator_names"] = np.array([str(x) for x in actuator_names])
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(target, actions=rows, **extra)
