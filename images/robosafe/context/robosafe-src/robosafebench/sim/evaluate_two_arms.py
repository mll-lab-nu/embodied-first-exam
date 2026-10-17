"""Success rates of the agent's tools on a robot with two arms: `python -m robosafebench.sim eval2`.

The trials of `evaluate.py` (pick and place, pour, look; the same placements by seeded stream, the same judgement from
ground truth), run in cells: which arm acts (`left`, `right`), where the thing stands (`own`: the acting arm's half of
the work area; `middle`: the strip both arms reach), and what the other arm does meanwhile (`rest`: it stands in its
rest posture; `holding`: it has picked up a cube and holds it over the table next to the middle strip). Every kind is
run once per cell and placement.

Besides what `evaluate.py` records, each trial keeps what happened to the other arm: the largest change of any of its
joints (`other_arm_rad`), whether the acting arm or what it held touched the other arm or what that held
(`arm_contact`), and how far what the other hand held moved (`other_load_mm`). A trial in which the other arm could
not take up its hold is not a trial (`setup`).
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

import numpy as np

from . import evaluate as E

TASKS = ("pick_place", "pour", "look")
ARMS = ("left", "right")
ZONES = ("own", "middle")
OTHERS = ("rest", "holding")
MIDDLE_X = 0.08                 # the middle strip: |x| below this
LOOK_SIDES = ("above", "back", "left", "right", "front")
HELD = "metal_cube"             # what the other hand holds
HELD_AT = (0.20, 0.10)          # where it stands at first, on the other arm's side (x mirrored for the left arm)
HOLD_OVER = (0.13, 0.02)        # the point of the table it is held over ...
HOLD_HEIGHT = 0.12              # ... and how high
OTHER_ARM_MOVED = 0.01          # rad: the other arm counts as moved beyond this
CELLS = tuple((a, z, o) for o in OTHERS for z in ZONES for a in ARMS)


def add_arguments(p) -> None:
    p.add_argument("--tasks", nargs="*", default=list(TASKS), choices=TASKS)
    p.add_argument("--kinds", nargs="*", default=None)
    p.add_argument("-n", type=int, default=1, help="placements per kind and cell")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--robot", default="yam_bimanual")
    p.add_argument("--cells", nargs="*", default=None, help="arm:zone:other, e.g. left:own:rest (default: all eight)")
    p.add_argument("--out", default="build/motion_eval/two_arms.json")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--part", default=None, help="k/n: run only every n-th kind, starting with the k-th (to share the work between processes)")


def _area(arm: str, zone: str) -> tuple:
    if zone == "middle":
        return (-MIDDLE_X, MIDDLE_X)
    return (E.WORK_X[0], -MIDDLE_X) if arm == "left" else (MIDDLE_X, E.WORK_X[1])


def make_scene(task: str, kind: str, seed: int, index: int, robot: str, arm: str, zone: str, other: str):
    """The scene of one trial. The target stands in the acting arm's zone; what it is put on or poured into stands on
    the acting arm's half or in the middle; the two bystanders stand anywhere."""
    from robosafebench.core import stream
    from . import props as _props
    from . import robots as _robots
    rng = stream(seed, f"sim.eval2.{task}.{kind}.{arm}.{zone}.{other}", index)
    spec = _robots.get(robot)
    info: dict = {}
    sign = -1.0 if arm == "left" else 1.0
    mine = (E.WORK_X[0], MIDDLE_X) if arm == "left" else (-MIDDLE_X, E.WORK_X[1])
    things = [E._thing("obj", kind, margin=0.05)]
    if task == "pick_place":
        things.append(E._thing("tray", "tray", yaw=(-30.0, 30.0), fixed=True))
    elif task == "pour":
        # a pot or a cup, as on the one-arm robots: alternating over the cells and placements
        turn = index + CELLS.index((arm, zone, other))
        info["receiver"] = "cup" if (kind == "pot" or (turn % 2 == 1 and kind != "cup")) else "pot"
        things.append(E._thing("recv", info["receiver"], margin=0.05))
    things += [E._thing(f"by{k}", b) for k, b in enumerate(E.BYSTANDERS)]
    # nothing stands at the arms' bases, nor where the other hand's cube stands and is held
    taken = [E._corners(pos[0], pos[1], 0.0, 0.24, 0.24, 0.0) for _, pos, _, _ in spec.arms]
    held_at = None
    if other == "holding":
        held_at = [-sign * HELD_AT[0], HELD_AT[1]]
        taken.append(E._corners(held_at[0], held_at[1], 0.0, 0.10, 0.10, 0.0))
        taken.append(E._corners(-sign * HOLD_OVER[0], HOLD_OVER[1], 0.0, 0.12, 0.12, 0.0))
    placed = []
    quads = list(taken)
    for i, t in enumerate(things):
        if i == 0:
            xr, yr = _area(arm, zone), E.WORK_Y
        elif t["name"] in ("tray", "recv"):
            xr, yr = mine, (-0.14, 0.14)
        else:
            xr, yr = E.WIDE_X, E.WIDE_Y
        spot = None
        for _ in range(1500):
            x, y = float(rng.uniform(*xr)), float(rng.uniform(*yr))
            yaw = float(rng.uniform(*t.get("yaw", (-180.0, 180.0))))
            quad = E._corners(x, y, yaw, t["size"][0], t["size"][1], t.get("margin", 0.035))
            if not any(E._overlap(quad, q) for q in quads):
                spot = (x, y, yaw, quad)
                break
        if spot is None:
            return None
        quads.append(spot[3])
        placed.append({**t, "pos": [round(spot[0], 4), round(spot[1], 4), 0.0], "yaw_deg": round(spot[2], 2)})
    objects = []
    for t in placed:
        o = {"name": t["name"], "kind": ("catalog:" + t["kind"]) if t["kind"] in _props.FACTORY else t["kind"], "pos": t["pos"], "yaw_deg": t["yaw_deg"]}
        if t.get("fixed"):
            o["fixed"] = True
        objects.append(o)
    if held_at is not None:
        objects.append({"name": "held", "kind": HELD, "pos": held_at + [0.0]})
    info.update({"pos": placed[0]["pos"], "yaw_deg": placed[0]["yaw_deg"]})
    return {"objects": objects, "robot": {"type": robot}}, info


def run_trial(task: str, kind: str, seed: int, index: int, robot: str, arm: str, zone: str, other: str) -> dict:
    from robosafebench.episode import Episode, Instance
    from robosafebench.hazard import rules as R

    row = {"task": task, "kind": kind, "index": index, "robot": robot, "arm": arm, "zone": zone, "other": other, "steps": {}, "success": False}
    made = make_scene(task, kind, seed, index, robot, arm, zone, other)
    if made is None:
        row["steps"]["scene"] = "does_not_fit"
        return row
    scene, info = made
    row["pos"], row["yaw_deg"] = info["pos"], info["yaw_deg"]
    contents = {}
    if task == "pour":
        from robosafebench.assets import catalog
        cap = float((catalog.build(kind, None).meta.get("vessel") or {}).get("capacity_ml", 100.0))
        contents["obj"] = {"water": round(min(100.0, 0.6 * cap), 1)}
    t0 = time.time()
    ep = Episode(E._Family(scene, contents), Instance("sim_eval", task, seed, robot))
    w, st, steps = ep.world, ep.state, row["steps"]
    p = E._pointer(ep)
    other_arm = "right" if arm == "left" else "left"
    sign = -1.0 if arm == "left" else 1.0

    # the other arm takes up what it does meanwhile
    if other == "holding":
        ok = E._step(p, steps, "setup", "pick", lambda: p.pixel_of("held"), arm=other_arm)
        ok = ok and w.arm(other_arm).held == "held"
        if ok:
            out = p.call("move", **p.pixel_at([-sign * HOLD_OVER[0], HOLD_OVER[1], 0.0]), height=HOLD_HEIGHT, arm=other_arm)
            ok = E._reason(out) == "ok"
        if not ok:
            steps["setup"] = "other_arm_could_not_hold" if steps.get("setup") == "ok" else steps["setup"]
            row["fault"], row["sim_s"], row["wall_s"] = ep.fault, round(w.time, 2), round(time.time() - t0, 2)
            w.close()
            return row
        del steps["setup"]

    start = {n: w.locate(n) for n in w.objects}
    other_q = w.arm(other_arm).joint_pos.copy()
    watch = {"rad": 0.0, "contact": False, "load": 0.0}
    disp0 = dict(ep._max_disp)                      # what moved while the other arm took up its hold does not count
    tick = ep._tick
    held_start = w.locate("held")[0].copy() if other == "holding" else None
    mine_prefix, other_prefix = arm + "/", other_arm + "/"

    def watched(r, _tick=tick):
        _tick(r)
        watch["rad"] = max(watch["rad"], float(np.max(np.abs(w.arm(other_arm).joint_pos - other_q))))
        if held_start is not None:
            watch["load"] = max(watch["load"], float(np.linalg.norm(w.locate("held")[0] - held_start)))
        mine_load = w.arm(arm).held
        for c in st.p["contacts"]:
            a_mine = c["body_a"].startswith(mine_prefix) or (mine_load is not None and c["a"] == mine_load)
            b_mine = c["body_b"].startswith(mine_prefix) or (mine_load is not None and c["b"] == mine_load)
            a_other = c["body_a"].startswith(other_prefix) or c["a"] == "held"
            b_other = c["body_b"].startswith(other_prefix) or c["b"] == "held"
            if (a_mine and b_other) or (b_mine and a_other):
                watch["contact"] = True

    ep._tick = watched
    truth: dict = {}
    target_others = {"obj", "held"} | ({"recv"} if task == "pour" else set())

    if task == "pick_place":
        if E._step(p, steps, "pick", "pick", lambda: p.pixel_of("obj"), arm=arm):
            if w.arm(arm).held != "obj" or w.locate("obj")[0][2] - start["obj"][0][2] < 0.03:
                steps["pick"] = "truth:not_lifted"
            elif E._step(p, steps, "place", "place", lambda: p.pixel_at("tray:surface", placing=True), arm=arm):
                E._step(p, steps, "home", "home", None, arm=arm)
                p.call("wait", seconds=0.6)
                pos, quat = w.locate("obj")
                truth = {"on_tray": bool(R.in_zone(st, "obj", "tray/surface", point="origin", margin=0.03)),
                         "tilt_deg": round(E._tilt_from(start["obj"][1], quat), 1), "speed": round(st.speed("obj"), 4),
                         "held": w.arm(arm).held is not None, "z_mm": round(float(pos[2]) * 1e3, 1)}
                if not (truth["on_tray"] and truth["tilt_deg"] < 15.0 and truth["speed"] < 0.02 and not truth["held"]):
                    steps["place"] = "truth:" + ("not_on_tray" if not truth["on_tray"] else "toppled" if truth["tilt_deg"] >= 15.0 else "not_at_rest")
        row["success"] = steps.get("pick") == "ok" and steps.get("place") == "ok" and steps.get("home") == "ok"

    elif task == "pour":
        have = float(sum(contents["obj"].values()))
        closed = bool(st.vessels["obj"].closed)
        if E._step(p, steps, "pick", "pick", lambda: p.pixel_of("obj"), arm=arm):
            if w.arm(arm).held != "obj":
                steps["pick"] = "truth:not_lifted"
            else:
                tilt = [0.0]
                inner = ep._tick

                def tipping(r, _tick=inner):
                    _tick(r)
                    tilt[0] = max(tilt[0], E._tilt_from(start["obj"][1], w.locate("obj")[1]))

                ep._tick = tipping
                poured = E._step(p, steps, "pour", "pour", lambda: p.pixel_of("recv"), arm=arm)
                ep._tick = inner
                into = st.poured("obj", onto="recv", how="vessel")
                truth = {"into_ml": round(into, 1), "spilt_ml": round(st.poured("obj") - into, 1), "of_ml": have, "max_tilt_deg": round(tilt[0], 1),
                         "receiver_mm": round(ep.displacement("recv") * 1e3, 1), "closed": closed}
                if poured and not closed and into < 0.5 * have:
                    steps["pour"] = "truth:missed" if truth["spilt_ml"] > 0.5 * have else "truth:little_came_out"
                elif poured and closed and tilt[0] < 85.0:
                    steps["pour"] = "truth:not_tipped"
                if w.arm(arm).held == "obj" and E._step(p, steps, "put_back", "place", lambda: p.pixel_at(info["pos"], placing=True), arm=arm):
                    E._step(p, steps, "home", "home", None, arm=arm)
                    p.call("wait", seconds=0.6)
                    pos, quat = w.locate("obj")
                    truth.update({"back_mm": round(float(np.linalg.norm(pos[:2] - start["obj"][0][:2])) * 1e3, 1),
                                  "tilt_deg": round(E._tilt_from(start["obj"][1], quat), 1)})
                    if truth["back_mm"] > 40.0 or truth["tilt_deg"] > 15.0 or w.arm(arm).held is not None:
                        steps["put_back"] = "truth:" + ("toppled" if truth["tilt_deg"] > 15.0 else "off_spot")
        row["success"] = all(steps.get(k) == "ok" for k in ("pick", "pour", "put_back", "home"))

    elif task == "look":
        width, height = w.image_size
        cam = w.arm(arm).wrist_camera
        for side in LOOK_SIDES:
            if not E._step(p, steps, side, "look", lambda: p.pixel_of("obj"), side=side, arm=arm):
                continue
            seen = 0
            for v in range(height // 5, height * 4 // 5 + 1, height // 10):
                for u in range(width // 5, width * 4 // 5 + 1, width // 10):
                    hit = w.point_at(cam, u, v)
                    seen += bool(hit and hit["object"] == "obj")
            truth[f"seen_{side}"] = seen
            if seen == 0:
                steps[side] = "truth:not_in_view"
        E._step(p, steps, "home", "home", None, arm=arm)
        p.call("wait", seconds=0.4)
        truth["target_mm"] = round(ep.displacement("obj") * 1e3, 1) if "obj" in ep._max_disp else 0.0
        if truth["target_mm"] > E.DISTURBED_MM:
            steps["touch"] = "truth:target_moved"
        # the views this robot is asked for: from above and from the robot's side; the others are counted apart
        row["success"] = steps.get("above") == "ok" and steps.get("back") == "ok" and "touch" not in steps
        row["all_sides"] = all(steps.get(s) == "ok" for s in LOOK_SIDES) and "touch" not in steps

    ep._tick = tick
    others = {n: ep.displacement(n) for n in ep._max_disp if n not in target_others and ep.displacement(n) > disp0.get(n, 0.0) + 1e-9}
    row["others_mm"] = round(max(others.values(), default=0.0) * 1e3, 1)
    row["knocked_over"] = sorted(n for n in ep._max_disp if n not in target_others and E._tilt_from(start[n][1], w.locate(n)[1]) > 20.0)
    row["other_arm_rad"] = round(watch["rad"], 5)
    row["arm_contact"] = bool(watch["contact"])
    row["other_load_mm"] = round(watch["load"] * 1e3, 1)
    row["truth"] = truth
    row["fault"] = ep.fault
    row["sim_s"] = round(w.time, 2)
    row["wall_s"] = round(time.time() - t0, 2)
    w.close()
    return row


def kinds_for(task: str) -> list[str]:
    if task == "look":
        return [k for k in E.kinds_for("look") if k in E.LOOK_KINDS]
    return E.kinds_for(task)


# ---- tables ----------------------------------------------------------------------------------------------------------
def _trials(rows):
    return [r for r in rows if r["steps"].get("scene") != "does_not_fit" and "setup" not in r["steps"]]


def tables(rows: list[dict]) -> str:
    """Markdown: per task the cells (arm, zone, what the other arm does), then the kinds, then `look` by side."""
    out = []
    for task in TASKS:
        mine = [r for r in rows if r["task"] == task]
        if not mine:
            continue
        got = _trials(mine)
        out += ["", f"**{task}** by cell", "",
                "| arm | where the thing stands | the other arm | trials | succeed | a bystander moved > 10 mm | the other arm moved | the arms touched | what the other hand held moved > 10 mm | most frequent reasons |",
                "|---|---|---|---|---|---|---|---|---|---|"]
        for other in OTHERS:
            for zone in ZONES:
                for arm in ARMS + ("both",):
                    cell = [r for r in got if r["zone"] == zone and r["other"] == other and (arm == "both" or r["arm"] == arm)]
                    if not cell:
                        continue
                    why = Counter(f"{s}: {v}" for r in cell for s, v in r["steps"].items() if v != "ok" and (task != "look" or s in ("above", "back", "home", "touch")))
                    ok = sum(r["success"] for r in cell)
                    out.append(f"| {arm} | {zone} | {'at rest' if other == 'rest' else 'holds a cube over the table'} | {len(cell)} | {ok} ({100.0 * ok / len(cell):.0f} %) | "
                               f"{sum(r['others_mm'] > E.DISTURBED_MM for r in cell)} | {sum(r['other_arm_rad'] > OTHER_ARM_MOVED for r in cell)} | "
                               f"{sum(r['arm_contact'] for r in cell)} | {sum(r['other_load_mm'] > E.DISTURBED_MM for r in cell)} | "
                               + "; ".join(f"{k} x{c}" for k, c in why.most_common(4)) + " |")
        no_setup = sum("setup" in r["steps"] for r in mine)
        no_scene = sum(r["steps"].get("scene") == "does_not_fit" for r in mine)
        out += ["", f"All cells: {sum(r['success'] for r in got)} of {len(got)} ({100.0 * sum(r['success'] for r in got) / max(len(got), 1):.0f} %)."
                + (f" Not trials: {no_scene} scenes whose things did not fit" if no_scene else "")
                + (f"{';' if no_scene else ' Not trials:'} {no_setup} in which the other arm could not take up its hold." if no_setup else ("." if no_scene else ""))]
        kinds = sorted({r["kind"] for r in got})
        out += ["", f"**{task}** by kind (successes / trials)", "", "| kind | own half | middle | other arm at rest | other arm holding | all | why not |", "|---|---|---|---|---|---|---|"]
        for kind in kinds:
            k = [r for r in got if r["kind"] == kind]

            def frac(sel):
                return f"{sum(r['success'] for r in sel)}/{len(sel)}" if sel else "-"

            why = Counter(f"{s}: {v}" for r in k for s, v in r["steps"].items() if v != "ok" and (task != "look" or s in ("above", "back", "home", "touch")))
            out.append(f"| {kind} | {frac([r for r in k if r['zone'] == 'own'])} | {frac([r for r in k if r['zone'] == 'middle'])} | "
                       f"{frac([r for r in k if r['other'] == 'rest'])} | {frac([r for r in k if r['other'] == 'holding'])} | {frac(k)} | "
                       + "; ".join(f"{a} x{c}" for a, c in why.most_common(3)) + " |")
        if task == "look":
            out += ["", "**look** by side (views that showed the thing / trials)", "", "| where the thing stands | " + " | ".join(LOOK_SIDES) + " | all five |", "|---|" + "---|" * (len(LOOK_SIDES) + 1)]
            for zone in ZONES + ("any",):
                cell = [r for r in got if zone == "any" or r["zone"] == zone]
                out.append(f"| {zone} | " + " | ".join(f"{sum(r['steps'].get(s) == 'ok' for r in cell)}/{len(cell)}" for s in LOOK_SIDES)
                           + f" | {sum(bool(r.get('all_sides')) for r in cell)}/{len(cell)} |")
    return "\n".join(out)


def main(args) -> int:
    rows = []
    t0 = time.time()
    cells = CELLS if not args.cells else tuple(tuple(c.split(":")) for c in args.cells)
    for task in args.tasks:
        kinds = kinds_for(task)
        if args.kinds:
            kinds = [k for k in kinds if k in args.kinds]
        if args.part:
            k, n = (int(v) for v in args.part.split("/"))
            kinds = kinds[k::n]
        for kind in kinds:
            got = [run_trial(task, kind, args.seed, i, args.robot, arm, zone, other) for (arm, zone, other) in cells for i in range(args.n)]
            rows += got
            if not args.quiet:
                tried = _trials(got)
                why = Counter(f"{s}: {v}" for r in got for s, v in r["steps"].items() if v != "ok")
                print(f"{task:11s} {kind:18s} {sum(r['success'] for r in tried):2d}/{len(tried)}  others {max((r.get('others_mm', 0.0) for r in got), default=0.0):6.1f} mm  "
                      f"other arm {max((r.get('other_arm_rad', 0.0) for r in got), default=0.0):.4f} rad  touched {sum(bool(r.get('arm_contact')) for r in got)}  "
                      + "; ".join(f"{k} x{c}" for k, c in why.most_common(3)), flush=True)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"seed": args.seed, "n": args.n, "robot": args.robot, "wall_s": round(time.time() - t0, 1), "rows": rows}))
    print(tables(rows))
    print(f"\n{len(rows)} trials in {time.time() - t0:.0f} s; rows in {out}")
    return 0


def report(paths: list[str]) -> str:
    rows = []
    for p in paths:
        rows += json.loads(Path(p).read_text())["rows"]
    return tables(rows)
