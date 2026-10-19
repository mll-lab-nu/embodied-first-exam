"""The pictures a probe is shown (docs/DIAGNOSE.md, "Probe").

For a trial: the record is replayed call by call (docs/REPLAY.md) and, at the call after which a part of the family's
evidence was before a camera for the first time (the episode's own bookkeeping, the one behind the verdict's
`evidence_seen`), that camera is rendered; after a `look` the enlarged image `detail` the agent was given is added.
Only what was in view before the decision moment counts. When the evidence was never completely in view, or the record
does not replay with this code, the pictures are the opening `front` and `top` images.

For a scene no trial has visited (`instance_frames`): an `observe`, then the calls of the hazard member's reference up
to its last `look`; the same calls and the same cameras are used for the family's other members, so that a twin is
shown from where the hazard scene was.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

OPENING = ("front", "top")
CAPTIONS = {"front": "from the camera in front of the table", "top": "from the camera above the table, looking straight down",
            "wrist": "from the camera on the robot's hand, held close to one of the things",
            "detail": "the view of the camera on the robot's hand, enlarged",
            # the enlarged picture is the pointing camera's when the hand cannot see the spot (Episode._detail_view)
            "detail_front": "the view of the camera in front of the table, enlarged", "detail_top": "the view of the camera above the table, enlarged"}


def _opening(ep) -> list[dict]:
    return [{"call": -1, "camera": cam, "kind": cam, "part": None, "image": ep.world.render(cam)} for cam in OPENING]


def shoot(key: dict, calls: list[dict], *, upto_tick: int | None = None, plan: list[dict] | None = None, check: bool = True) -> dict:
    """Replay `calls` in a fresh episode of `key` and return `{"basis", "why", "shots", "plan"}`.

    Without `plan`: `basis` is `evidence` when every part of one evidence item came into view (no later than
    `upto_tick`), and the shots are the cameras that had the parts in view, taken then; else `opening`
    (`opening_other_version` when the record did not replay: the pictures are then of this code's scene).
    With `plan` (`[{"call", "camera", "kind"}]`, call -1 = the opening state): exactly those pictures, `basis` `plan`.
    `check`: stop when a call's result differs from the digest in the record (the record is of another version)."""
    from robosafebench import verify
    try:
        fam, inst, ep = verify.start(key)
    except Exception as e:                         # a member or family this version does not have
        return {"basis": "none", "why": f"{type(e).__name__}: {str(e)[:120]}", "shots": [], "plan": []}
    try:
        opening = _opening(ep)
        shots, done, why = [], set(), None
        want = {(p["call"], p["kind"]) for p in plan} if plan is not None else None
        if want is not None:
            shots += [s for s in opening if (-1, s["kind"]) in want]
        last = max((p["call"] for p in plan), default=-1) if plan is not None else None
        for i, c in enumerate(calls):
            if last is not None and i > last:
                break
            if plan is None and upto_tick is not None and c.get("tick0") is not None and c["tick0"] > upto_tick:
                break
            out = ep.execute({"tool": c["tool"], "args": json.loads(json.dumps(c.get("args") or {}))})
            if check and c.get("digest") is not None and ep.calls[-1]["digest"] != c["digest"]:
                why = f"the record does not replay with this code (call {i}: {c['tool']})"
                break
            images = out.get("images") or {}
            if want is not None:
                for kind in ("front", "top", "wrist", "detail"):
                    if (i, kind) in want:
                        img = images.get(kind) if kind == "detail" else ep.world.render(kind)
                        if img is None and kind == "detail" and ep.looked_at is not None:
                            img = ep.world.render_detail(*ep._detail_view())
                        if img is not None:
                            shots.append({"call": i, "camera": _detail_camera(ep) if kind == "detail" else kind, "kind": kind, "part": None, "image": img})
                continue
            for part, got in sorted(ep._evidence_parts.items()):
                if part in done or (upto_tick is not None and got["tick"] > upto_tick):
                    continue
                done.add(part)
                cam = got["camera"]
                if any(s["call"] == i and s["kind"] == cam and s["part"][0] == part[0] for s in shots):
                    continue                    # two parts of one item in one camera's view at one call: one picture
                image = ep.world.render_detail(*ep._detail_view()) if cam == "detail" else ep.world.render(cam)
                shots.append({"call": i, "camera": _detail_camera(ep) if cam == "detail" else cam,
                              "kind": cam, "part": part, "image": image})
                if cam == "wrist" and c["tool"] == "look" and out.get("ok") and ep.looked_at is not None:
                    shots.append({"call": i, "camera": _detail_camera(ep), "kind": "detail", "part": part,
                                  "image": images.get("detail") if images.get("detail") is not None else ep.world.render_detail(*ep._detail_view())})
            seen = ep.evidence_seen
            if seen is not None and (upto_tick is None or seen["tick"] <= upto_tick):
                break
        if plan is not None:
            basis = "plan"
        else:
            seen = ep.evidence_seen
            if why is None and seen is not None and (upto_tick is None or seen["tick"] <= upto_tick):
                parts = fam.evidence(inst)
                item = next(k for k, it in enumerate(parts) if [p["at"] for p in (it if isinstance(it, (list, tuple)) else [it])] == seen["at"])
                shots = [s for s in shots if s["part"][0] == item]
                basis = "evidence"
            else:
                basis, shots = ("opening_other_version" if why else "opening"), opening
                why = why or ("the evidence was never completely in view of a camera before the decision moment" if parts_of(fam, inst) else "the family names no evidence")
        return {"basis": basis, "why": why, "shots": shots, "plan": [{"call": s["call"], "camera": s["camera"], "kind": s["kind"]} for s in shots]}
    finally:
        ep.world.close()


def _detail_camera(ep) -> str:
    """The camera whose view the image `detail` enlarges after the last `look` (the wrist camera, as a rule)."""
    try:
        view = ep._detail_view()
        return str(view[2]) if len(view) > 2 else "wrist"
    except Exception:
        return "wrist"


def parts_of(fam, inst) -> list:
    from robosafebench.hazard import view
    return view.parts(fam.evidence(inst))


def trial_frames(record: dict, upto_tick: int | None = None) -> dict:
    """The pictures for a trial's record: the evidence as it came into view before `upto_tick`, else the opening."""
    return shoot(record["instance"], record.get("calls") or [], upto_tick=upto_tick)


def hazard_member(fam) -> str:
    return "hazard_unnamed" if "hazard_unnamed" in fam.members else next(m for m in fam.members if fam.roles.get(m) == "hazard")


def instance_frames(key: dict) -> dict:
    """The pictures for a scene without a trial (see the module's text). The result also names the `source` member."""
    from robosafebench import families, verify
    fam = families.get(key["family"])
    hkey = {**key, "member": hazard_member(fam)}
    ref = verify.run(hkey, "reference")["calls"]
    looks = [i for i, c in enumerate(ref) if c["tool"] == "look"]
    # the opening `observe` asks for no pictures: the reference after it is a scripted caller, judged on the pictures each
    # of its calls would have returned (0.5.4, `Episode._look_for_evidence`; a first call that returned pictures would
    # make its `look`, which asks for none, count for nothing)
    calls = [{"tool": "observe", "args": {"images": False}}] + [{"tool": c["tool"], "args": c["args"]} for c in ref[:looks[-1] + 1]] if looks else [{"tool": "observe", "args": {"images": False}}]
    got = shoot(hkey, calls, check=False)
    if key["member"] != hkey["member"]:
        got = {**shoot(key, calls, plan=got["plan"], check=False), "basis": got["basis"], "why": got["why"]}
    return {**got, "source": hkey["member"]}


TOLERANCE = 0.5     # grey levels of a 16 x 16 block mean: two pictures closer than this everywhere are the same picture


def thumbnail(image):
    """The picture as the means of its 16 x 16 blocks (rows x columns x 3, float). Two renders of one state are not
    the same bytes: measured here, up to 48 pixels of a 640 x 480 picture were one level off, which moves a block
    mean by at most 0.04; a hazard scene and its twin differ by 20 levels and more in some block. So pictures are
    compared by these means, within `TOLERANCE`, and never by a hash of their bytes."""
    import numpy as np
    if isinstance(image, (bytes, bytearray)):
        from robosafebench.sim.png import decode_png
        image = decode_png(bytes(image))
    a = np.asarray(image)[..., :3].astype(np.float64)
    h, w = (a.shape[0] // 16) * 16, (a.shape[1] // 16) * 16
    return a[:h, :w].reshape(h // 16, 16, w // 16, 16, 3).mean(axis=(1, 3))


def pack(thumb) -> str:
    """A thumbnail as text for the cache: its shape and the means in 64ths of a level."""
    import numpy as np
    return "x".join(str(n) for n in thumb.shape) + ":" + base64.b64encode(np.round(np.asarray(thumb) * 64.0).astype("<u2").tobytes()).decode()


def unpack(text: str):
    import numpy as np
    shape, data = text.split(":", 1)
    return np.frombuffer(base64.b64decode(data), dtype="<u2").astype(np.float64).reshape([int(n) for n in shape.split("x")]) / 64.0


def same_picture(a: str, b: str, tolerance: float = TOLERANCE) -> bool:
    """Two packed thumbnails are of the same picture: the same size, and no block mean further apart than `tolerance`."""
    import numpy as np
    if a == b:
        return True
    try:
        x, y = unpack(a), unpack(b)
    except Exception:
        return False
    return x.shape == y.shape and float(np.abs(x - y).max()) <= tolerance


def save(shots: list[dict], out: Path, stem: str) -> list[dict]:
    """Write the shots as PNG files `<stem>_<n>_<kind>.png` under `out`: `[{"path", "thumb", "kind", "caption", "call"}]`."""
    from robosafebench.sim.png import encode_png
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    files = []
    for n, s in enumerate(shots):
        data = s["image"] if isinstance(s["image"], (bytes, bytearray)) else encode_png(s["image"])
        path = out / f"{stem}_{n}_{s['kind']}.png"
        path.write_bytes(data)
        caption = s["kind"] if s["kind"] != "detail" or s.get("camera", "wrist") == "wrist" else f"detail_{s['camera']}"
        files.append({"path": str(path), "thumb": pack(thumbnail(s["image"])), "kind": s["kind"], "caption": caption, "call": s["call"]})
    return files


def captions(files: list[dict]) -> str:
    """One line per picture, in the order they are attached."""
    return "\n".join(f"{n}. {CAPTIONS[f.get('caption') or f['kind']]}" for n, f in enumerate(files, start=1))
