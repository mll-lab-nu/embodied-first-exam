"""Randomised check scenarios for the skills: a scene, a scripted use of the skills and a ground-truth verdict.

Used by the tests, by `python -m robosafebench.sim` and for the success rates quoted in `docs/MOTION.md`. Each scenario is a pure
function of `(seed, index)`: every random number comes from `robosafebench.core.rng.stream(seed, "sim.<scenario>", index)`.
The verdicts read privileged state; the skills' own statuses do not, and are reported next to them.
"""
from __future__ import annotations

from typing import Callable

import numpy as np

from robosafebench.core import stream

from . import skills, tf
from .props import hole_names
from .world import World

Hook = Callable[[World], None] | None


def _yaw_xy(rng, x_range, y_range, yaw_range_deg) -> tuple[list[float], float]:
    x = float(rng.uniform(*x_range))
    y = float(rng.uniform(*y_range))
    return [x, y, 0.0], float(rng.uniform(*yaw_range_deg))


# ---- tube from one rack hole to another ----------------------------------------------------------------------------
def tube_transfer_scene(seed: int, index: int) -> tuple[dict, dict]:
    rng = stream(seed, "sim.tube_transfer", index)
    pos, yaw = _yaw_xy(rng, (-0.20, 0.20), (-0.14, 0.08), (-30.0, 30.0))
    rows, cols = 2, 4
    names = hole_names(rows, cols)
    picks = [names[int(i)] for i in rng.permutation(len(names))[:3]]
    src, dst, other = picks
    scene = {"objects": [
        {"name": "rack", "kind": "tube_rack", "params": {"rows": rows, "cols": cols}, "pos": pos, "yaw_deg": yaw},
        {"name": "tube", "kind": "tube", "at": f"rack/hole_{src}"},
        {"name": "tube_b", "kind": "tube", "params": {"cap_rgba": "0.15 0.45 0.85 1"}, "at": f"rack/hole_{other}"},
    ]}
    return scene, {"source": src, "target": dst, "bystander": other, "rack_yaw_deg": yaw}


def tube_in_hole(world: World, tube: str, rack: str, hole: str) -> dict:
    """Ground truth: is the tube standing in that hole, let go of and at rest?"""
    p = world.privileged()
    t = p["objects"][tube]
    floor, _ = p["sites"][f"{rack}/hole_{hole}"]
    rack_pose = (p["objects"][rack]["pos"], p["objects"][rack]["quat"])
    rel = tf.compose(tf.inverse(rack_pose), (t["pos"], t["quat"]))[0] - tf.compose(tf.inverse(rack_pose), (floor, [1, 0, 0, 0]))[0]
    half = world.objects[rack]["meta"]["hole_half"]
    tilt = tf.tilt_deg(tf.quat_mul(tf.quat_conj(rack_pose[1]), t["quat"]))
    touching = any("robot" in (c["a"], c["b"]) and tube in (c["a"], c["b"]) for c in p["contacts"])
    out = {"dx_mm": float(rel[0]) * 1e3, "dy_mm": float(rel[1]) * 1e3, "dz_mm": float(rel[2]) * 1e3, "tilt_deg": tilt,
           "speed": float(np.linalg.norm(t["linvel"])), "released": not touching,
           "opening_mm": world.gripper_opening() * 1e3}
    out["success"] = bool(abs(rel[0]) < half and abs(rel[1]) < half and abs(rel[2]) < 0.004 and tilt < 8.0
                          and out["speed"] < 0.01 and out["released"] and out["opening_mm"] > 25.0)
    return out


def run_tube_transfer(seed: int, index: int, on_step: Hook = None, world_kwargs: dict | None = None,
                      pose_noise: float = 0.0) -> dict:
    """`pose_noise` (m): the skills are told the tube and the target hole are up to this far (in x and in y) from
    where they really are, as an imperfect pose estimate would."""
    scene, info = tube_transfer_scene(seed, index)
    world = World(scene, **(world_kwargs or {}))
    skills.run(world, skills.hold(world, 0.2), on_step)
    off = stream(seed, "sim.tube_transfer.noise", index).uniform(-1.0, 1.0, size=(2, 2)) * float(pose_noise)
    info["pose_noise_mm"] = (off * 1e3).tolist()
    seen = world.locate("tube/grip_0")
    seen[0][:2] += off[0]
    # the fingers close across the rack (its y direction), where the neighbouring holes are furthest away
    grasp = {"type": "top", "yaw_deg": info["rack_yaw_deg"] + 90.0, "pose": seen}
    # carry the tube high enough for its lower end to pass over the caps of the tubes standing in the rack
    carry = world.objects["tube"]["meta"]["total_length"] + 0.03
    s_pick = skills.run(world, skills.pick(world, "tube", grasp, lift=carry), on_step)
    s_place = skills.Status(False, "skipped")
    if s_pick.ok:
        target = world.locate(f"rack/hole_{info['target']}")
        target[0][:2] += off[1]
        s_place = skills.run(world, skills.place(world, "tube", target, approach=carry), on_step)
    skills.run(world, skills.hold(world, 0.5), on_step)
    truth = tube_in_hole(world, "tube", "rack", info["target"])
    by = tube_in_hole(world, "tube_b", "rack", info["bystander"])
    truth["bystander_undisturbed"] = bool(abs(by["dx_mm"]) < 12 and abs(by["dy_mm"]) < 12 and by["tilt_deg"] < 8.0)
    truth["success"] = bool(truth["success"] and truth["bystander_undisturbed"])
    return {"scenario": "tube_transfer", "seed": seed, "index": index, "info": info, "pick": s_pick, "place": s_place,
            "truth": truth, "success": truth["success"], "world": world}


# ---- beaker: side grasp, tilt to 60 degrees and back ---------------------------------------------------------------
def beaker_tilt_scene(seed: int, index: int) -> tuple[dict, dict]:
    rng = stream(seed, "sim.beaker_tilt", index)
    pos, yaw = _yaw_xy(rng, (-0.22, 0.22), (-0.12, 0.08), (-180.0, 180.0))
    scene = {"objects": [{"name": "beaker", "kind": "beaker", "pos": pos, "yaw_deg": yaw}]}
    return scene, {"angle_deg": 60.0, "rate_deg_s": 30.0}


def run_beaker_tilt(seed: int, index: int, on_step: Hook = None, world_kwargs: dict | None = None) -> dict:
    scene, info = beaker_tilt_scene(seed, index)
    world = World(scene, **(world_kwargs or {}))
    seen = {"max_tilt": 0.0}

    def watch(w: World) -> None:
        seen["max_tilt"] = max(seen["max_tilt"], tf.tilt_deg(w.locate("beaker")[1]))
        if on_step is not None:
            on_step(w)

    skills.run(world, skills.hold(world, 0.2), watch)
    s_pick = skills.run(world, skills.pick(world, "beaker", "side", lift=0.06), watch)
    s_tilt = s_back = skills.Status(False, "skipped")
    at_peak = 0.0
    if s_pick.ok:
        s_tilt = skills.run(world, skills.tilt(world, "beaker", info["angle_deg"], info["rate_deg_s"]), watch)
        skills.run(world, skills.hold(world, 0.3), watch)
        at_peak = tf.tilt_deg(world.locate("beaker")[1])
        if s_tilt.ok:
            s_back = skills.run(world, skills.tilt(world, "beaker", 0.0, info["rate_deg_s"]), watch)
    skills.run(world, skills.hold(world, 0.3), watch)
    p = world.privileged()
    b = p["objects"]["beaker"]
    grip_pos = world.locate("beaker/grip_0")[0]
    slip = float(np.linalg.norm(grip_pos - world.tcp_pose()[0]))
    truth = {"tilt_at_peak_deg": at_peak, "max_tilt_deg": seen["max_tilt"], "final_tilt_deg": tf.tilt_deg(b["quat"]),
             "height_mm": float(b["pos"][2]) * 1e3, "slip_mm": slip * 1e3, "held": skills.holding(world)}
    truth["success"] = bool(abs(at_peak - info["angle_deg"]) < 4.0 and truth["final_tilt_deg"] < 4.0
                            and truth["height_mm"] > 20.0 and slip < 0.012 and truth["held"])
    return {"scenario": "beaker_tilt", "seed": seed, "index": index, "info": info, "pick": s_pick, "tilt": s_tilt,
            "back": s_back, "truth": truth, "success": truth["success"], "world": world}


# ---- push button ---------------------------------------------------------------------------------------------------
def button_press_scene(seed: int, index: int) -> tuple[dict, dict]:
    rng = stream(seed, "sim.button_press", index)
    pos, yaw = _yaw_xy(rng, (-0.25, 0.25), (-0.15, 0.10), (-180.0, 180.0))
    scene = {"objects": [{"name": "button", "kind": "button", "pos": pos, "yaw_deg": yaw}]}
    return scene, {"depth": 0.006}


def run_button_press(seed: int, index: int, on_step: Hook = None, world_kwargs: dict | None = None) -> dict:
    scene, info = button_press_scene(seed, index)
    world = World(scene, **(world_kwargs or {}))
    seen = {"deepest": 0.0}

    def watch(w: World) -> None:
        seen["deepest"] = min(seen["deepest"], float(w.data.qpos[w.model.joint("button/press").qposadr[0]]))
        if on_step is not None:
            on_step(w)

    skills.run(world, skills.hold(world, 0.2), watch)
    s_press = skills.run(world, skills.press(world, "button/top", info["depth"]), watch)
    skills.run(world, skills.hold(world, 0.3), watch)
    final = world.privileged()["joints"]["button/press"]["pos"]
    truth = {"deepest_mm": -seen["deepest"] * 1e3, "final_mm": -final * 1e3}
    truth["success"] = bool(abs(truth["deepest_mm"] - info["depth"] * 1e3) < 1.5 and truth["final_mm"] < 0.5)
    return {"scenario": "button_press", "seed": seed, "index": index, "info": info, "press": s_press, "truth": truth,
            "success": truth["success"], "world": world}


# ---- pour, then put the beaker back where it stood ---------------------------------------------------------------
def put_down_scene(seed: int, index: int) -> tuple[dict, dict]:
    """A source beaker in front of the robot, the receiver
    0.18 to 0.24 m to one side on the 20 mm pan of a scale, mirrored half the time."""
    g = stream(seed, "sim.put_down", index)
    sx, sy = float(g.uniform(0.02, 0.20)), float(g.uniform(-0.12, 0.02))
    rx, ry = sx - float(g.uniform(0.18, 0.24)), sy + float(g.uniform(-0.05, 0.05))
    if float(g.uniform()) < 0.5:
        sx, rx = -sx, -rx
    scene = {"objects": [
        {"name": "source", "kind": "beaker", "pos": [sx, sy, 0.0]},
        {"name": "pan", "kind": "block", "params": {"size": [0.14, 0.14, 0.02], "mass": 0.5, "rgba": "0.82 0.84 0.86 1"},
         "pos": [rx, ry, 0.0], "fixed": True},
        {"name": "receiver", "kind": "beaker", "pos": [rx, ry, 0.02]},
    ]}
    return scene, {"angle_deg": float(g.uniform(55.0, 80.0)), "spot": [sx, sy, 0.0]}


def run_put_down(seed: int, index: int, on_step: Hook = None, world_kwargs: dict | None = None,
                 positioning: str = "move_to") -> dict:
    """Pick the source by its side, bring its lip over the receiver, tilt and tilt back, then `place` it where it
    stood and go home.

    `positioning`: "move_to" brings the lip over the receiver the way `robosafebench.bench.ArmDevice.position_to_pour` does
    (a straight tool move with the full IK); "carry" uses `skills.position_to_pour`.
    The verdict: the source stands upright on its spot, let go of; it never tilted more than 3 degrees between
    tilting back and being let go; nothing touched the receiver and it did not move; the arm is back home.
    """
    scene, info = put_down_scene(seed, index)
    world = World(scene, **(world_kwargs or {}))
    seen = {"phase": "pour", "carry_tilt": 0.0, "receiver_touched": False}

    def watch(w: World) -> None:
        p = w.privileged()
        if seen["phase"] == "carry":
            seen["carry_tilt"] = max(seen["carry_tilt"], tf.tilt_deg(p["objects"]["source"]["quat"]))
        for c in p["contacts"]:
            if "receiver" in (c["a"], c["b"]) and "pan" not in (c["a"], c["b"]):
                seen["receiver_touched"] = True
        if on_step is not None:
            on_step(w)

    rcv0 = world.locate("receiver")[0]
    skills.run(world, skills.hold(world, 0.3), watch)
    s_pick = skills.run(world, skills.pick(world, "source", "side", lift=0.17), watch)
    s_pos = s_tilt = s_back = s_place = s_home = skills.Status(False, "skipped")
    if s_pick.ok:
        if positioning == "carry":
            s_pos = skills.run(world, skills.position_to_pour(world, "source", "receiver"), watch)
            pour = s_pos.info if s_pos.ok else None
        else:
            v = world.objects["source"]["meta"]["vessel"]
            tcp = world.tcp_pose()
            axis = tf.rotate(tcp[1], [0.0, 0.0, 1.0])
            lean = tf.unit(np.cross(axis, [0.0, 0.0, 1.0]))
            src_rim, dst_rim = world.locate("source/rim")[0], world.locate("receiver/rim")[0]
            sign = 1.0 if float(np.dot((dst_rim - src_rim)[:2], lean[:2])) >= 0.0 else -1.0
            lip = src_rim + sign * v["inner_radius"] * lean
            aim = dst_rim - sign * 0.010 * lean
            shift = np.array([aim[0] - lip[0], aim[1] - lip[1], 0.0])
            s_pos = skills.run(world, skills.move_to(world, (tcp[0] + shift, tcp[1]), linear=True, speed=0.5), watch)
            pour = {"axis": axis, "pivot": lip + shift, "sign": sign}
        if s_pos.ok:
            s_tilt = skills.run(world, skills.tilt(world, "source", pour["sign"] * info["angle_deg"], 40.0,
                                                   axis=pour["axis"], pivot=pour["pivot"]), watch)
            skills.run(world, skills.hold(world, 0.5), watch)
            if s_tilt.ok:
                s_back = skills.run(world, skills.tilt(world, "source", 0.0, 90.0, axis=pour["axis"], pivot=pour["pivot"]), watch)
                skills.run(world, skills.hold(world, 0.5), watch)
        if s_back.ok:
            seen["phase"] = "carry"
            s_place = skills.run(world, skills.place(world, "source", (info["spot"], [1.0, 0.0, 0.0, 0.0])), watch)
            seen["phase"] = "after"
            if s_place.ok:
                s_home = skills.run(world, skills.move_joints(world, world.home), watch)
    skills.run(world, skills.hold(world, 1.0), watch)
    p, q = world.locate("source")
    truth = {"off_spot_mm": float(np.linalg.norm(p[:2] - np.array(info["spot"][:2]))) * 1e3, "height_mm": float(p[2]) * 1e3,
             "tilt_deg": tf.tilt_deg(q), "carry_tilt_deg": seen["carry_tilt"], "held": skills.holding(world),
             "receiver_touched": seen["receiver_touched"],
             "receiver_moved_mm": float(np.linalg.norm(world.locate("receiver")[0] - rcv0)) * 1e3,
             "home_err": float(np.max(np.abs(world.joint_pos - world.home)))}
    truth["success"] = bool(truth["off_spot_mm"] < 5.0 and abs(truth["height_mm"]) < 2.0 and truth["tilt_deg"] < 2.0
                            and truth["carry_tilt_deg"] < 3.0 and not truth["held"] and not truth["receiver_touched"]
                            and truth["receiver_moved_mm"] < 1.0 and truth["home_err"] < 0.01)
    return {"scenario": "put_down", "seed": seed, "index": index, "info": info, "pick": s_pick, "position": s_pos,
            "tilt": s_tilt, "back": s_back, "place": s_place, "home": s_home, "truth": truth,
            "success": truth["success"], "world": world}


# ---- measurement rigs ---------------------------------------------------------------------------------------------
MASS_SET = (0.010, 0.020, 0.050, 0.100, 0.200)       # kg


def _in_frame(pose: tf.Pose, local) -> list[float]:
    return [float(v) for v in tf.compose(pose, (np.asarray(local, dtype=np.float64), np.array([1.0, 0, 0, 0])))[0]]


def balance_load_scene(seed: int, index: int) -> tuple[dict, dict]:
    g = stream(seed, "sim.balance_load", index)
    pos, yaw = _yaw_xy(g, (-0.15, 0.10), (-0.20, -0.06), (-20.0, 20.0))
    stiffness = float(g.uniform(50.0, 90.0))
    mass = float(MASS_SET[int(g.integers(len(MASS_SET)))])
    slot = int(g.integers(5))
    frame = (np.array(pos), tf.quat_yaw(np.radians(yaw)))
    balance = {"name": "balance", "kind": "spring_balance", "params": {"stiffness": stiffness}, "pos": pos, "yaw_deg": yaw}
    objects = [balance,
               {"name": "mass", "kind": "mass_block", "params": {"mass": mass},
                "pos": _in_frame(frame, [float(g.uniform(0.20, 0.30)), float(g.uniform(-0.06, 0.10)), 0.0]), "yaw_deg": yaw}]
    already = 0.0
    if float(g.uniform()) < 0.5:             # something stands on the pan already, two slots away or more
        other = [k for k in range(5) if abs(k - slot) >= 2]
        fits = [m for m in MASS_SET if (m + mass) * 9.81 / stiffness < 0.075]     # the pan has 90 mm of travel
        already = float(fits[int(g.integers(len(fits)))])
        balance["joints"] = {"spring": -already * 9.81 / stiffness}      # the pan starts where that load holds it
        objects.append({"name": "other", "kind": "mass_block", "params": {"mass": already},
                        "at": f"balance/slot_{other[int(g.integers(len(other)))]}", "offset": [0.0, 0.0, -already * 9.81 / stiffness]})
    # no grasp assist: the wrist has to feel the weight of what the fingers hold, which the assist compensates
    scene = {"assist": False, "objects": objects, "sensors": [
        {"name": "pointer", "kind": "displacement", "site": "balance/pointer", "relative_to": "balance/scale_zero", "record": True},
        {"name": "touch", "kind": "contact_timer", "a": "robot", "b": "mass"}]}
    return scene, {"stiffness": stiffness, "mass": mass, "slot": slot, "already": already, "yaw_deg": yaw}


def run_balance_load(seed: int, index: int, on_step: Hook = None, world_kwargs: dict | None = None) -> dict:
    """Take a mass block from the table and set it on the pan of the spring balance (`set_on`).

    Success: the block stands upright on its slot, let go of; the pointer comes to rest at the deflection the masses
    on the pan call for, m g / stiffness, within 0.2 mm or 1 %; and the pan was not set swinging: in the second
    after the fingers opened the pointer moved by less than 1.5 mm peak to peak (`truth["swing_mm"]`; typically 0.5).
    """
    scene, info = balance_load_scene(seed, index)
    world = World(scene, **(world_kwargs or {}))
    pointer = world.sensors["pointer"]
    skills.run(world, skills.hold(world, 1.0), on_step)                       # the pan settles under what is on it
    s_pick = skills.run(world, skills.pick(world, "mass", {"type": "top", "yaw_deg": info["yaw_deg"] + 90.0}), on_step)
    s_set = skills.Status(False, "skipped")
    if s_pick.ok:
        s_set = skills.run(world, skills.set_on(world, "mass", f"balance/slot_{info['slot']}"), on_step)
    released = s_set.info.get("released_at") or world.time
    skills.run(world, skills.hold(world, 2.0), on_step)
    after = np.array([v for t, v in pointer.samples if released <= t <= released + 1.0])
    expect = -(info["mass"] + info["already"]) * world.scene["gravity"] / info["stiffness"]
    slot = world.locate(f"balance/slot_{info['slot']}")
    p, q = world.locate("mass")
    rel = tf.compose(tf.inverse(slot), (p, q))[0]
    truth = {"pointer_mm": pointer.read() * 1e3, "expected_mm": expect * 1e3,
             "swing_mm": float(after.max() - after.min()) * 1e3 if after.size else 99.0,
             "off_slot_mm": float(np.linalg.norm(rel[:2])) * 1e3, "above_pan_mm": float(rel[2]) * 1e3,
             "tilt_deg": tf.tilt_deg(q), "held": skills.holding(world), "touching": world.sensors["touch"].touching}
    err = abs(truth["pointer_mm"] - truth["expected_mm"])
    truth["success"] = bool(err < max(0.2, 0.01 * abs(truth["expected_mm"])) and truth["swing_mm"] < 1.5
                            and truth["off_slot_mm"] < 3.0 and abs(truth["above_pan_mm"]) < 1.0 and truth["tilt_deg"] < 1.0
                            and not truth["held"] and not truth["touching"])
    return {"scenario": "balance_load", "seed": seed, "index": index, "info": info, "pick": s_pick, "set_on": s_set,
            "truth": truth, "success": truth["success"], "world": world}


def incline_release_scene(seed: int, index: int) -> tuple[dict, dict]:
    g = stream(seed, "sim.incline_release", index)
    pos, yaw = _yaw_xy(g, (-0.12, 0.12), (-0.33, -0.25), (75.0, 105.0))
    angle = float(g.uniform(15.0, 30.0))
    mu = float(g.uniform(0.08, 0.24))
    frame = (np.array(pos), tf.quat_yaw(np.radians(yaw)))
    block_at = _in_frame(frame, [float(g.uniform(0.02, 0.22)), float(g.choice([-1.0, 1.0])) * float(g.uniform(0.13, 0.20)), 0.0])
    scene = {"assist": False, "objects": [
        {"name": "ramp", "kind": "incline", "params": {"angle_deg": angle, "friction": mu}, "pos": pos, "yaw_deg": yaw},
        {"name": "slider", "kind": "block", "params": {"size": [0.04, 0.04, 0.036], "mass": 0.08, "friction": mu},
         "pos": block_at, "yaw_deg": yaw}],
        "sensors": [{"name": f"gate_{k}", "kind": "light_gate", "track": "slider", "plane": f"ramp/gate_{k}", "axis": "x", "radius": 0.06}
                    for k in (0, 1)] + [{"name": "touch", "kind": "contact_timer", "a": "robot", "b": "slider"}]}
    return scene, {"angle_deg": angle, "friction": mu, "yaw_deg": yaw}


def run_incline_release(seed: int, index: int, on_step: Hook = None, world_kwargs: dict | None = None) -> dict:
    """Take a block from the table, set it on the ramp at the `start` site and let it slide (`set_on`).

    Success: the block passed both light gates going down, flat on the ramp (never more than 3 degrees off it up to
    the second gate); the acceleration worked out from the two gate times, taking it to have started from rest at
    `start`, is within 4 % of g (sin a - mu cos a); and the gripper touched it once only.
    """
    scene, info = incline_release_scene(seed, index)
    world = World(scene, **(world_kwargs or {}))
    gates = world.objects["ramp"]["meta"]["gates"]
    seen = {"off_ramp": 0.0}

    def watch(w: World) -> None:
        touch = w.sensors["touch"]
        if touch.intervals and not touch.touching and not w.sensors["gate_1"].crossings:      # let go, not yet through
            rel = tf.quat_mul(tf.quat_conj(w.locate("ramp/start")[1]), w.locate("slider")[1])
            seen["off_ramp"] = max(seen["off_ramp"], tf.tilt_deg(rel))
        if on_step is not None:
            on_step(w)

    skills.run(world, skills.hold(world, 0.2), watch)
    # the fingers close across the ramp, so that the block leaves between them when it slides
    s_pick = skills.run(world, skills.pick(world, "slider", {"type": "top", "yaw_deg": info["yaw_deg"] + 90.0}), watch)
    s_set = skills.Status(False, "skipped")
    if s_pick.ok:
        s_set = skills.run(world, skills.set_on(world, "slider", "ramp/start"), watch)
    skills.run(world, skills.hold(world, 1.5), watch)
    a = np.radians(info["angle_deg"])
    expect = world.scene["gravity"] * (np.sin(a) - info["friction"] * np.cos(a))
    down = [[c["t"] for c in world.sensors[f"gate_{k}"].crossings if c["direction"] < 0] for k in (0, 1)]
    touch = world.sensors["touch"]
    truth = {"accel": 0.0, "expected": float(expect), "off_ramp_deg": seen["off_ramp"], "touches": len(touch.intervals),
             "passed": [len(d) for d in down]}
    if down[0] and down[1]:
        dt = down[1][0] - down[0][0]
        truth["accel"] = float(2.0 * (np.sqrt(gates[1]) - np.sqrt(gates[0])) ** 2 / dt ** 2)
    truth["success"] = bool(truth["passed"] == [1, 1] and abs(truth["accel"] / expect - 1.0) < 0.04
                            and truth["off_ramp_deg"] < 3.0 and truth["touches"] == 1)
    return {"scenario": "incline_release", "seed": seed, "index": index, "info": info, "pick": s_pick, "set_on": s_set,
            "truth": truth, "success": truth["success"], "world": world}


def release_in_place_scene(seed: int, index: int) -> tuple[dict, dict]:
    g = stream(seed, "sim.release_in_place", index)
    what = ("table", "stack", "hanging")[int(g.integers(3))]
    mass = float(MASS_SET[int(g.integers(len(MASS_SET)))])
    if what == "hanging":
        pos, yaw = _yaw_xy(g, (-0.12, 0.12), (-0.34, -0.27), (75.0, 105.0))
        k = int(g.integers(3))
        scene = {"objects": [{"name": "rig", "kind": "pendulum_rig", "params": {"bob_mass": mass}, "pos": pos, "yaw_deg": yaw}]}
        return scene, {"what": what, "mass": mass, "pendulum": k}
    pos, yaw = _yaw_xy(g, (-0.20, 0.20), (-0.20, 0.02), (-45.0, 45.0))
    objects = [{"name": "mass", "kind": "mass_block", "params": {"mass": mass}, "pos": pos, "yaw_deg": yaw}]
    if what == "stack":
        objects = [{"name": "under", "kind": "mass_block", "params": {"mass": 0.1}, "pos": pos, "yaw_deg": yaw},
                   {"name": "mass", "kind": "mass_block", "params": {"mass": mass}, "at": "under/top"}]
    return {"objects": objects}, {"what": what, "mass": mass, "yaw_deg": yaw}


def run_release_in_place(seed: int, index: int, on_step: Hook = None, world_kwargs: dict | None = None) -> dict:
    """Close the fingers on something that rests (a block on the table, or on another block) or hangs (a pendulum bob)
    without lifting it, then `release` it.

    Success: after the release the object is where it was before it was touched: a resting block within 0.3 mm and
    0.3 degrees (and the block under it likewise), a bob never more than 0.5 degrees off its rest position in the two
    seconds that follow; the fingers are clear of it.
    """
    scene, info = release_in_place_scene(seed, index)
    world = World(scene, **(world_kwargs or {}))
    skills.run(world, skills.hold(world, 0.5), on_step)
    hanging = info["what"] == "hanging"
    if hanging:
        k = info["pendulum"]
        qa = int(world.model.joint(f"rig/swing_{k}").qposadr[0])
        grasp, obj = {"type": "side", "site": f"grip_{k}"}, "rig"
    else:
        grasp, obj = {"type": "top", "yaw_deg": info["yaw_deg"] + 90.0}, "mass"
        before = {n: world.locate(n) for n in world.objects}
    s_grasp = skills.run(world, skills.pick(world, obj, grasp, lift=0.0, squeeze=0.01), on_step)
    s_release = skills.Status(False, "skipped")
    swing = [0.0]

    def watch(w: World) -> None:
        if hanging:
            swing[0] = max(swing[0], abs(float(np.degrees(w.data.qpos[qa]))))
        if on_step is not None:
            on_step(w)

    if s_grasp.ok:
        s_release = skills.run(world, skills.release(world), watch)
    skills.run(world, skills.hold(world, 2.0), watch)
    touching = any("robot" in (c["a"], c["b"]) and obj in (c["a"], c["b"]) for c in world.privileged()["contacts"])
    truth = {"moved_mm": 0.0, "turned_deg": 0.0, "swing_deg": swing[0], "touching": touching, "held": skills.holding(world)}
    if not hanging:
        for n, (p0, q0) in before.items():
            p1, q1 = world.locate(n)
            truth["moved_mm"] = max(truth["moved_mm"], float(np.linalg.norm(p1 - p0)) * 1e3)
            truth["turned_deg"] = max(truth["turned_deg"], float(np.degrees(np.linalg.norm(tf.rotvec(q0, q1)))))
    truth["success"] = bool(s_grasp.ok and truth["moved_mm"] < 0.3 and truth["turned_deg"] < 0.3 and truth["swing_deg"] < 0.5
                            and not touching and not truth["held"])
    return {"scenario": "release_in_place", "seed": seed, "index": index, "info": info, "grasp": s_grasp,
            "release": s_release, "truth": truth, "success": truth["success"], "world": world}


RUNNERS = {"tube_transfer": run_tube_transfer, "beaker_tilt": run_beaker_tilt, "button_press": run_button_press,
           "put_down": run_put_down, "balance_load": run_balance_load, "incline_release": run_incline_release,
           "release_in_place": run_release_in_place}


def evaluate(name: str, seed: int, n: int, **kwargs) -> dict:
    """Run a scenario on `n` placements and count the ground-truth successes."""
    rows = []
    for k in range(n):
        r = RUNNERS[name](seed, k, **kwargs)
        r["world"].close()
        statuses = {key: (v.ok, v.reason) for key, v in r.items() if isinstance(v, skills.Status)}
        rows.append({"index": k, "success": r["success"], "statuses": statuses, "truth": r["truth"], "info": r["info"],
                     "sim_seconds": r["world"].time})
    return {"scenario": name, "seed": seed, "n": n, "successes": sum(r["success"] for r in rows), "trials": rows}


def _fmt(x) -> str:
    return f"{x:.2f}" if isinstance(x, float) else str(x)


def summary_line(trial: dict) -> str:
    st = " ".join(f"{k}={'ok' if ok else why}" for k, (ok, why) in trial["statuses"].items())
    tr = " ".join(f"{k}={_fmt(v)}" for k, v in trial["truth"].items() if k != "success")
    return f"#{trial['index']:02d} {'PASS' if trial['success'] else 'FAIL'}  {st}  |  {tr}"

