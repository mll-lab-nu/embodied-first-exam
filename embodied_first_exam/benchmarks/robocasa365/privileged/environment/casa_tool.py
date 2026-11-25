"""RoboCasa-series tooling: one robosuite / RoboCasa kitchen environment on a frozen instance.

Used by the privileged agent (importable as `casa_tool`), by the privileged verifier, and by the standard-mode sim
service (images/<benchmark>/standard/server_casa.py).

    import casa_tool
    s = casa_tool.Session("/app/instance.npz")  # the frozen instance; s.env is the robosuite env, s.model/s.data MuJoCo
    s.action_spec                               # the native controller's channels: names, units, limits, frames
    st = s.state()                              # privileged state: instruction, joints, every body's pose, objects
    r = s.step(action)                          # one native control step (1/20 s) -> {"success", "control_steps", ...}
    s.save_trajectory()                         # the actions since the last reset -> /app/output/trajectory.npz
    s.replay(actions)                           # reset, then replay (what the verifier does) -> {"success", "state_sha"}
    s.reset()                                   # back to the frozen start, as often as you like
    img = s.render("robot0_agentview_center")   # RGB (240, 320, 3); views in s.camera_views

Actions are the robot's native composite-controller commands, one row per control step, in the layout of
s.action_spec (clipped to its limits). Success is the environment's own check (`_check_success`) on the state after
the last action. The check runs exactly twice after every control step and once at reset (the call pattern the
frozen instances and references were validated with): some checks keep timers, so the pattern is part of the task.
"""

from __future__ import annotations

import copy
import ctypes
import glob
import hashlib
import json
import os
import random
import zipfile
from pathlib import Path

import mujoco
import numpy as np
import robocasa  # noqa: F401  (registers the kitchen environments)
import robosuite


def _disable_mesh_cache() -> None:
    """MuJoCo keeps a process-wide cache of compiled meshes (mj_globalCache). A mesh served from it can differ from a
    freshly compiled one (mesh_polynormal), so a scene built twice in one process could step differently from a scene
    built once, depending on what the process loaded before. With the cache off, every build compiles its meshes
    afresh, exactly as the first build in a fresh process does: one behaviour for the agent, verifier and service.
    Determinism depends on it, so a MuJoCo build without these symbols is an error, never a silent no-op."""
    libs = glob.glob(os.path.join(os.path.dirname(mujoco.__file__), "libmujoco.so*"))
    if not libs:
        raise RuntimeError(f"casa_tool: no libmujoco.so next to {mujoco.__file__}; cannot turn off the mesh cache")
    lib = ctypes.CDLL(libs[0])
    missing = [s for s in ("mj_globalCache", "mj_setCacheSize") if not hasattr(lib, s)]
    if missing:
        raise RuntimeError(
            f"casa_tool: {libs[0]} (MuJoCo {mujoco.__version__}) has no {', '.join(missing)}; the mesh cache cannot be "
            "turned off and replays would not be deterministic (this tooling is pinned to MuJoCo 3.3.1)"
        )
    lib.mj_globalCache.restype = ctypes.c_void_p
    lib.mj_setCacheSize.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    lib.mj_setCacheSize(lib.mj_globalCache(), 0)


_disable_mesh_cache()

INSTANCE_SCHEMA = "rcb-casa-instance-v1"
STATE_SPEC = mujoco.mjtState.mjSTATE_INTEGRATION
# Model arrays the kitchen's reset rewrites (fixture and object placement): part of the frozen instance.
MODEL_FIELDS = (
    "body_pos",
    "body_quat",
    "site_pos",
    "site_quat",
    "geom_pos",
    "geom_quat",
    "geom_size",
    "eq_data",
    "geom_rgba",
    "site_rgba",
)
MAX_STEPS = 3000  # privileged deliverable: at most this many control steps (the references' authoring cap)
ROBOT_PREFIXES = ("robot0_", "mobilebase0_", "gripper0_")
CAMERA_PREFERENCE = (
    "robot0_agentview_center",
    "robot0_agentview_left",
    "robot0_agentview_right",
    "egoview",
    "robot0_eye_in_hand",
    "robot0_eye_in_right_hand",
    "robot0_eye_in_left_hand",
)


# -- frozen instances -------------------------------------------------------------------------------------------
def encode(x):
    """JSON-safe encoding of numpy values, sets, tuples and dicts (raises TypeError for anything else)."""
    if isinstance(x, np.ndarray):
        if x.dtype.hasobject:
            raise TypeError("object array")
        return {"__array__": x.tolist(), "dtype": x.dtype.str}
    if isinstance(x, np.generic):
        return x.item()
    if isinstance(x, (set, frozenset)):
        values = sorted((encode(v) for v in x), key=lambda v: json.dumps(v, sort_keys=True))
        return {"__frozenset__" if isinstance(x, frozenset) else "__set__": values}
    if isinstance(x, tuple):
        return {"__tuple__": [encode(v) for v in x]}
    if isinstance(x, list):
        return [encode(v) for v in x]
    if isinstance(x, dict):
        if any(not isinstance(k, str) for k in x):
            raise TypeError("non-string key")
        return {k: encode(v) for k, v in x.items()}
    if x is None or isinstance(x, (int, float, str, bool)):
        return x
    raise TypeError(type(x).__name__)


def decode(x):
    if isinstance(x, dict):
        if "__set__" in x:
            return set(decode(v) for v in x["__set__"])
        if "__frozenset__" in x:
            return frozenset(decode(v) for v in x["__frozenset__"])
        if "__array__" in x:
            return np.asarray(x["__array__"], dtype=x["dtype"])
        if "__tuple__" in x:
            return tuple(decode(v) for v in x["__tuple__"])
        return {k: decode(v) for k, v in x.items()}
    if isinstance(x, list):
        return [decode(v) for v in x]
    return x


def caches(obj) -> dict:
    out = {}
    for k, v in vars(obj).items():
        try:
            value = encode(v)
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError):
            continue
        out[k] = value
    return out


def graph(env) -> dict:
    """The env's Python objects whose attributes make up the task state (no pickle, no dotted eval)."""
    out = {"env": env}
    for k, v in env.fixtures.items():
        out["fixture:" + k] = v
    for i, r in enumerate(env.robots):
        out["robot:" + str(i)] = r
        out["composite:" + str(i)] = r.composite_controller
        for k, v in r.part_controllers.items():
            out[f"controller:{i}:{k}"] = v
        for k, v in r.gripper.items():
            out[f"gripper:{i}:{k}"] = v
        for k, v in vars(r).items():
            if type(v).__module__ == "robosuite.utils.buffers":
                out[f"buffer:{i}:{k}"] = v
    for k, v in env._observables.items():
        out["observable:" + k] = v
    return out


def raw(env):
    return env.sim.model._model, env.sim.data._data


def physical(env) -> dict:
    m, d = raw(env)
    state = np.empty(mujoco.mj_stateSize(m, STATE_SPEC))
    mujoco.mj_getState(m, d, state, STATE_SPEC)
    out = {"integration": state}
    out.update({"model_" + k: getattr(m, k).copy() for k in MODEL_FIELDS})
    return out


def snapshot(env) -> dict:
    g = graph(env)
    out = physical(env)
    out["caches"] = np.array(json.dumps({k: caches(v) for k, v in g.items()}, sort_keys=True, allow_nan=False))
    out["attribute_names"] = np.array(json.dumps({k: sorted(vars(v)) for k, v in g.items()}, sort_keys=True))
    out["rng"] = np.array(json.dumps(encode(env.rng.bit_generator.state), sort_keys=True))
    out["global_rng"] = np.array(json.dumps(encode(np.random.get_state()), sort_keys=True))
    out["python_rng"] = np.array(json.dumps(encode(random.getstate())))
    return out


def restore(env, frozen: dict) -> None:
    m, d = raw(env)
    for k in MODEL_FIELDS:
        getattr(m, k)[:] = frozen["model_" + k]
    # Rebuilding from XML can create lazy task history (e.g. ScrubBowl.prev_sponge_pos): restore its absence too.
    if "attribute_names" in frozen:
        objects = graph(env)
        for name, names in json.loads(str(frozen["attribute_names"])).items():
            obj = objects[name]
            for key in set(vars(obj)) - set(names):
                delattr(obj, key)
    for name, values in decode(json.loads(str(frozen["caches"]))).items():
        obj = graph(env)[name]
        for k, v in values.items():
            setattr(obj, k, v)
    env.rng.bit_generator.state = decode(json.loads(str(frozen["rng"])))
    np.random.set_state(decode(json.loads(str(frozen["global_rng"]))))
    random.setstate(decode(json.loads(str(frozen["python_rng"]))))
    mujoco.mj_setState(m, d, frozen["integration"], STATE_SPEC)
    mujoco.mj_forward(m, d)
    mujoco.mj_setState(m, d, frozen["integration"], STATE_SPEC)  # forward changes warm-start fields: set them again


def make_env(config: dict, meta: dict | None = None, xml: str | None = None):
    random.seed(0)
    np.random.seed(0)
    kw = copy.deepcopy(config)
    kw.update(has_renderer=False, has_offscreen_renderer=False, use_camera_obs=False, seed=0)
    env = robosuite.make(**kw)
    if meta is not None:
        env.set_ep_meta(copy.deepcopy(meta))
    env.reset()
    if xml is not None:
        env.reset_from_xml_string(env.edit_model_xml(xml))
        env.sim.reset()
    return env


def digest(data: dict) -> str:
    sha = hashlib.sha256()
    for key, value in sorted(data.items()):
        arr = np.ascontiguousarray(value)
        sha.update(key.encode())
        sha.update(arr.dtype.str.encode())
        sha.update(str(arr.shape).encode())
        sha.update(arr.tobytes())
    return sha.hexdigest()


def load_npz(path, max_bytes: int = 8_000_000) -> dict:
    """Pickle-free NPZ loader with size limits (trajectories come from the agent)."""
    path = Path(path)
    if path.stat().st_size > max_bytes:
        raise ValueError("archive too large")
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > 64 or sum(i.file_size for i in infos) > 8 * max_bytes:
            raise ValueError("expanded archive too large")
        if any(not i.filename.endswith(".npy") for i in infos):
            raise ValueError("expected .npy members only")
    with np.load(path, allow_pickle=False) as data:
        return {k: data[k].copy() for k in data.files}


def load_instance(path) -> tuple[dict, str]:
    with np.load(path, allow_pickle=False) as z:
        data = {k: z[k].copy() for k in z.files}
    sha = str(data.pop("instance_sha"))
    if str(data.get("schema")) != INSTANCE_SCHEMA or digest(data) != sha:
        raise ValueError(f"{path}: not a valid frozen instance (hash mismatch)")
    return data, sha


def task_state(env) -> dict:
    """The task's own Python state (timers, previous positions, fixture flags), for the state hash."""
    skip = {"_obs_cache", "_ep_meta", "_cam_configs", "object_cfgs", "fixture_cfgs", "_curr_gen_fixtures"}
    tags = ("__array__", "__tuple__", "__set__", "__frozenset__")
    simple = {}
    for k, v in caches(env).items():
        if k in skip:
            continue
        if not isinstance(v, (dict, list, str)) or (isinstance(v, dict) and any(t in v for t in tags)):
            simple[k] = v
    fixture = {
        name: {k: v for k, v in caches(obj).items() if k.startswith("_") and isinstance(v, (int, float, bool))}
        for name, obj in env.fixtures.items()
    }
    return {"env": simple, "fixtures": fixture}


def state_hash(env) -> str:
    data = physical(env)
    data["task_state"] = np.array(json.dumps(task_state(env), sort_keys=True))
    return digest(data)


# -- the native action layout -------------------------------------------------------------------------------
def action_spec(env) -> dict:
    """Every channel of the robot's composite controller: name, unit, kind (delta | absolute | grip | mode), limits."""
    robot = env.robots[0]
    lo, hi = (np.asarray(x, float) for x in env.action_spec)
    dim = int(env.action_dim)
    if type(robot.robot_model).__name__ == "GR1ArmsAndWaistFourierHands":
        if dim != 24:
            raise ValueError("unsupported GR1 layout")
        names = [f"{arm}_{a}" for arm in ("right", "left") for a in ("x", "y", "z", "rx", "ry", "rz")]
        fingers = ("little", "ring", "middle", "index", "thumb_flexion", "thumb_rotation")
        names += [f"{arm}_{f}" for arm in ("right", "left") for f in fingers]
        units = ["m", "m", "m", "rad", "rad", "rad"] * 2 + ["hand_command"] * 12
        kinds = ["absolute"] * 24
        lower, upper = [-10.0] * 12 + [-3.0] * 12, [10.0] * 12 + [3.0] * 12
        frame = (
            "arm channels: absolute pose targets of each hand's grip site in the robot's base frame (XYZ metres, "
            "axis-angle radians), solved by the whole-body inverse-kinematics controller (mink); hand channels: "
            "unscaled Fourier hand commands, six per hand in the listed finger order (not a binary grip)"
        )
        parts = {"right": [0, 6], "left": [6, 12], "right_hand": [12, 18], "left_hand": [18, 24]}
    else:
        if dim not in (12, 13) or not (np.all(np.isfinite(lo)) and np.all(np.isfinite(hi))):
            raise ValueError("unsupported mobile Panda layout")
        parts = {k: list(v) for k, v in robot._action_split_indexes.items()}
        parts["hybrid_mode"] = [dim - 1, dim]
        if dim == 13:
            names = [f"arm_joint{i + 1}" for i in range(7)]
            units, kinds = ["rad"] * 7, ["absolute"] * 7
            frame = "arm channels: absolute joint position targets (rad); base and torso channels: robot base frame"
        else:
            names = ["arm_dx", "arm_dy", "arm_dz", "arm_drx", "arm_dry", "arm_drz"]
            units, kinds = ["normalised_translation"] * 3 + ["normalised_axis_angle"] * 3, ["delta"] * 6
            frame = (
                "arm channels: end-effector deltas in the robot base frame, scaled by the controller "
                "(1.0 = 5 cm / 0.5 rad per control step); base and torso channels: robot base frame"
            )
        names += ["grip", "base_x", "base_y", "base_yaw", "torso", "hybrid_mode"]
        units += ["normalised_grip", "normalised_velocity", "normalised_velocity", "normalised_yaw_velocity"]
        units += ["normalised_torso_velocity", "mode"]
        kinds += ["grip", "delta", "delta", "delta", "delta", "mode"]
        lower, upper = lo.tolist(), hi.tolist()
    if not (len(names) == len(units) == len(kinds) == dim):
        raise ValueError("action layout does not cover every channel")
    channels = [
        {"index": i, "name": n, "unit": u, "kind": k, "lower": lower[i], "upper": upper[i]}
        for i, (n, u, k) in enumerate(zip(names, units, kinds, strict=True))
    ]
    out = {
        "dim": dim,
        "control_hz": int(env.control_freq),
        "names": names,
        "lower": lower,
        "upper": upper,
        "channels": channels,
        "parts": parts,
        "frame": frame,
    }
    if dim in (12, 13):
        out["grip"] = "positive closes, negative opens"
        out["hybrid_mode"] = "> 0: base mode (the arm goal moves with the base); <= 0: arm mode (default -1)"
    return out


# -- task text -------------------------------------------------------------------------------------------------
# The frozen instance keeps the benchmark's own language string (ep_meta["lang"]); the instance file is pinned and is
# not edited. The text the agent is shown (Session.inst["text"]: the privileged state()["instruction"], the service's
# spec task_text and task info) is a plain sentence written for the instance, the same one as the task's
# instruction.md Task line: it names what the environment's own success check needs (which open cabinet, the
# gripper moved away where the check has that term) and leaves out where things start. Keyed by env_name and the
# exact upstream string, so any other instance of the family keeps its own text.
TEXT_ERRATA = {
    ("AddLemonToFish",
     "Take the lemon wedge from the fridge and place it on the plate with fish on the dining counter."):
        "Put the lemon wedge from the fridge on the plate with the fish on the dining counter, and move your hand"
        " away.",
    ("AssembleCookingArray",
     "Move the shrimp onto the pan on the stove. Then move the syrup bottle and broccoli from the cabinet to the "
     "counter where the plate is."):
        "Put the shrimp in the pan on the stove, and move the syrup bottle and the broccoli from the cabinet to "
        "the counter where the plate is, and move your hand away.",
    ("BeverageSorting",
     "Sort all alcoholic drinks to one cabinet, and non-alcoholic drinks to the other."):
        "Put the two alcoholic drinks in one of the two open cabinets and the two non-alcoholic drinks in the "
        "other, and move your hand away.",
    ("BreadAndCheese",
     "Place the bread and cheese on the cutting board."):
        "Put the bread and the cheese on the cutting board, and move your hand away.",
    ("CandleCleanup",
     "Pick the candle and jar from the dining table and place them in the open cabinet. Close the cabinet after "
     "placing the objects."):
        "Put the candle and the jar from the dining table in the open cabinet, then close that cabinet.",
    ("CerealAndBowl",
     "Open the cabinet. Pick the cereal and bowl from the cabinet and place them on the counter next to the milk."
     " Then close the cabinet."):
        "Take the cereal and the bowl out of the cabinet, put them on the counter next to it, and close the "
        "cabinet again.",
    ("ChooseMeasuringCup",
     "Open the right drawer and place the smaller measuring cup on the counter."):
        "Take the smaller measuring cup out of the drawer and put it on the counter next to that drawer, and move"
        " your hand away.",
    ("ClearFoodWaste",
     "Move the food items out of the sink and into the colander."):
        "Move the two food items from the sink into the colander, and move your hand away.",
    ("ClearSink",
     "Remove the corn and carrot from the sink. Then move the bowl and cup from the counter to the sink for "
     "washing."):
        "Take the corn and the carrot out of the sink and put the bowl and the cup from the counter in it, and "
        "move your hand away.",
    ("CloseDrawer",
     "Close the right drawer."):
        "Close the right drawer.",
    ("CloseOven",
     "Close the oven door."):
        "Close the oven door.",
    ("CloseStandMixerHead",
     "Close the stand mixer head."):
        "Close the stand mixer head.",
    ("CookieDoughPrep",
     "Pick the egg and butter from the fridge and place them by the bowl for mixing."):
        "Take the egg and the butter from the fridge and put them on the counter by the bowl, and move your hand "
        "away.",
    ("DeliverBrewedCoffee",
     "Pick up the brewed coffee from the coffee machine and place it next to the breakfast plate on the dining "
     "counter."):
        "Take the coffee from the coffee machine and put it on the dining counter next to the breakfast plate, "
        "and move your hand away.",
    ("DessertUpgrade",
     "Move the dessert items from the plates to the tray."):
        "Move the two desserts from the plates onto the tray, and move your hand away.",
    ("DisplayMeatVariety",
     "Retrieve the chicken drumstick, shrimp, and steak from the fridge and place them on the serving tray on the"
     " dining counter."):
        "Put the chicken drumstick, the shrimp and the steak from the fridge on the serving tray on the dining "
        "counter, and move your hand away.",
    ("DivideBasins",
     "Move any existing items from the left basin to the right basin for drying. Then move the cup from the "
     "counter to the left basin of the sink for washing."):
        "Move the item in the sink's left basin to the right basin, then put the cup from the counter in the left"
        " basin, and move your hand away.",
    ("DrainVeggies",
     "Dump the lettuce from the pot into the sink. Then turn on the water and wash the lettuce. Then turn off the"
     " water and put the lettuce back in the pot."):
        "Dump the lettuce from the pot into the sink, rinse it under running water, then turn the water off and "
        "put the lettuce back in the pot.",
    ("DrinkwareConsolidation",
     "Pick the bottled water from the counter and place it in the open cabinet."):
        "Put the bottled water from the counter in the open cabinet, and move your hand away.",
    ("MakeIceLemonade",
     "Grab a lemon wedge from the fridge and one ice cube from the ice bowl, and put them in the glass of "
     "lemonade."):
        "Put the lemon wedge from the fridge and an ice cube from the ice bowl in the glass of lemonade, and move"
        " your hand away.",
    ("MakeLoadedPotato",
     "Retrieve the reheated potato from the microwave, then place the potato, cheese, and condiment on the "
     "cutting board."):
        "Take the potato out of the microwave and put it, the cheese and the condiment on the cutting board, and "
        "move your hand away.",
    ("MealPrepStaging",
     "Place both pans onto different burners. Then place the corn and the steak on different pans."):
        "Put the two pans on two different burners, then put the corn in one pan and the steak in the other.",
    ("MicrowaveDefrostMeat",
     "Place the tupperware containing the frozen chicken drumstick in the microwave. Close the microwave door and"
     " press the start button to defrost the meat."):
        "Take the tupperware with the frozen chicken drumstick out of the freezer, put it in the microwave, close"
        " the door and press start, then move your hand away.",
    ("OpenDishwasher",
     "Open the dishwasher door."):
        "Open the dishwasher door all the way.",
    ("OrganizeCoffeeCondiments",
     "Pick the syrup bottle and honey bottle from the cabinet and place them next to the mug."):
        "Put the syrup bottle and the honey bottle from the cabinet on the counter next to the mug, and move your"
        " hand away.",
    ("OvenBroilFish",
     "Place the fish on the bottom rack of the oven, and slide the tray back inside. Close the oven door."):
        "Put the fish on the oven's bottom rack, slide the rack back in and close the oven door.",
    ("PackDessert",
     "Add the marshmallow to the tupperware that contains the hot dog."):
        "Put the marshmallow in the tupperware with the hot dog, and move your hand away.",
    ("PickPlaceCabinetToCounter",
     "Pick the ice cube from the cabinet and place it on the counter."):
        "Take the ice cube out of the cabinet and put it on the counter next to it, and move your hand away.",
    ("PickPlaceSinkToCounter",
     "Pick the egg from the sink and place it on the plate located on the counter."):
        "Take the egg out of the sink and put it on the plate on the counter, and move your hand away.",
    ("PlateSteakMeal",
     "Create a steak meal by picking up the steak and asparagus from the tray and placing them on the plate. "
     "Leave the chili pepper on the tray."):
        "Move the steak and the asparagus from the tray to the plate and leave the chili pepper on the tray, and "
        "move your hand away.",
    ("PortionInTupperware",
     "Place one cooked food and one vegetable from the large plate to each tupperware container."):
        "Put one cooked food and one vegetable from the large plate in each of the two tupperware containers, and"
        " move your hand away.",
    ("PreRinseStation",
     "Place the glass cup in the left basin and the kettle in the right basin of the sink."):
        "Put the glass cup in the sink's left basin and the kettle in its right basin, and move your hand away.",
    ("PrepForSanitizing",
     "Pick the bar soap and dish brush from the cabinet and place them on the counter."):
        "Take the bar soap and the dish brush out of the cabinet and put them on the counter next to it, and move"
        " your hand away.",
    ("PrepMarinatingMeat",
     "Pick the shrimp from the plate and place it on the cutting board. Then pick the condiment bottle from the "
     "cabinet and place it next to the cutting board."):
        "Put the shrimp from the plate on the cutting board, then put the condiment bottle from the cabinet next "
        "to the board, and move your hand away.",
    ("ReheatMeal",
     "Place the tupperware containing the shrimp and carrot meal in the microwave. Close the microwave door and "
     "press the start button to reheat the meal."):
        "Take the tupperware with the shrimp and carrot meal out of the fridge, put it in the microwave, close "
        "the door and press start, then move your hand away.",
    ("RetrieveMeat",
     "Retrieve the fish from the fridge and place it on the cutting board."):
        "Take the fish from the fridge and put it on the cutting board, and move your hand away.",
    ("SanitizePrepCuttingBoard",
     "Grab the spray bottle from the cabinet, then place it next to the cutting board for sanitizing. Then grab "
     "the dish brush from the countertop next to the sink and place it next to the cutting board."):
        "Put the spray bottle from the cabinet and the dish brush from beside the sink next to the cutting board,"
        " and move your hand away.",
    ("ScrubBowl",
     "Use the sponge to scrub the bowl inside the sink."):
        "Scrub the bowl in the sink with the sponge for a while, then move your hand away.",
    ("SearingMeat",
     "Grab the pan from the cabinet and place it on the rear right burner on the stove. Then place the chicken "
     "drumstick on the stove and turn the burner on."):
        "Put the pan from the cabinet on the stove's rear right burner, put the chicken drumstick in the pan and "
        "turn that burner on, then move your hand away.",
    ("SeasoningSpiceSetup",
     "Move the condiment bottle and ketchup from the cabinet to the dining counter."):
        "Move the condiment bottle and the ketchup from the cabinet to the dining counter, and move your hand "
        "away.",
    ("SetUpCuttingStation",
     "Pick up the knife from the drawer and place it on the cutting board. Then place the meat from the plate to "
     "the cutting board."):
        "Put the knife from the drawer and the meat from the plate on the cutting board, and move your hand away.",
    ("StockingBreakfastFoods",
     "Pick the canned food and bar from the counter and place them in the cabinets closest to them."):
        "Put the canned food and the bar from the counter each in the cabinet closest to it, and move your hand "
        "away.",
    ("SweetenCoffee",
     "Take a sugar cube from the saucer and place it inside the coffee. Then, grab milk from the fridge and place"
     " it next to the coffee on the counter to sweeten the coffee. "):
        "Put a sugar cube from the saucer in the coffee, and put the milk from the fridge on the counter next to "
        "the coffee, and move your hand away.",
    ("ThawInSink",
     "Pick the orange from the counter and place it in the sink. Then turn on the sink faucet."):
        "Put the orange from the counter in the sink and turn on the water.",
    ("TongBuffetSetup",
     "Take the tongs from the drawer on the left and place them on the dining counter next to the tray containing"
     " the hot dog."):
        "Take the tongs from the drawer and put them on the dining counter next to the tray with the hot dog, and"
        " move your hand away.",
    ("TurnOffMicrowave",
     "Press the stop button on the microwave."):
        "Press the microwave's stop button, then move your hand away.",
    ("TurnOnMicrowave",
     "Press the start button on the microwave."):
        "Press the microwave's start button, then move your hand away.",
    ("TurnOnSinkFaucet",
     "Turn on the sink faucet."):
        "Turn on the sink faucet.",
    ("TurnOnStove",
     "Turn on the rear left burner of the stove."):
        "Turn on the stove's rear left burner.",
    ("TurnOnToasterOven",
     "Turn on the toaster oven by setting the timer."):
        "Turn on the toaster oven by setting its timer.",
}


def task_text(env_name: str, lang: str) -> str:
    """The task sentence the agent is shown: the instance's plain sentence (TEXT_ERRATA), else its own language string."""
    return TEXT_ERRATA.get((env_name, lang), lang)


# -- the session ----------------------------------------------------------------------------------------------
def scene_option() -> mujoco.MjvOption:
    """What robosuite's own cameras draw (its defaults render_collision_mesh=False, render_visual_mesh=True): the visual
    geoms (group 1), not the collision geoms (group 0). MuJoCo's default MjvOption also draws group 0, which paints the
    collision shells over the scene (red fixtures, a green robot) and into the depth image."""
    opt = mujoco.MjvOption()
    opt.geomgroup[0] = 0
    opt.geomgroup[1] = 1
    return opt


class Session:
    mj = mujoco

    def __init__(self, instance="/app/instance.npz", enable_render: bool = False):
        self.instance_path = Path(instance)
        self.frozen, self.instance_sha = load_instance(self.instance_path)
        self.meta = json.loads(str(self.frozen["ep_meta"]))
        env_name = json.loads(str(self.frozen["config"]))["env_name"]
        self.inst = {"text": task_text(env_name, self.meta.get("lang", "")), "env_name": env_name}
        self.env = None
        self._renderers: dict = {}
        self.reset()
        self.action_spec = action_spec(self.env)
        self.action_dim = self.action_spec["dim"]
        self.action_names = self.action_spec["names"]
        self.lower = np.asarray(self.action_spec["lower"], float)
        self.upper = np.asarray(self.action_spec["upper"], float)
        self.control_dt = 1.0 / float(self.env.control_freq)
        cams = [self.model.camera(i).name for i in range(self.model.ncam)]
        self.camera_views = {c: {"camera": c} for c in CAMERA_PREFERENCE if c in cams}
        self.proprio_layout = self._proprio_layout()
        self.targets = self.initial_command()

    # -- episode -------------------------------------------------------------------------------------------------
    def reset(self) -> dict:
        """Back to the frozen start (bit-exact)."""
        f = self.frozen
        self._close_renderers()
        if self.env is not None:
            self.env.close()
        self.env = make_env(json.loads(str(f["config"])), copy.deepcopy(self.meta), str(f["xml"]))
        restore(self.env, f)
        self.actions: list[np.ndarray] = []
        self.success = bool(self.env._check_success())
        self.initial_success = self.success
        self.reward = 0.0
        if hasattr(self, "action_spec"):
            self.targets = self.initial_command()
        return self._report()

    def step(self, action) -> dict:
        """One native control step; the action is clipped to the controller's limits."""
        a = np.asarray(action, dtype=np.float64).reshape(-1)
        if a.shape != (self.action_dim,) or not np.all(np.isfinite(a)):
            raise ValueError(f"an action is {self.action_dim} finite numbers (see action_spec)")
        a = np.clip(a, self.lower, self.upper)
        _, reward, _, _ = self.env.step(a.copy())
        self.env._check_success()  # first of the two checks per step (see the module docstring)
        self.success = bool(self.env._check_success())
        self.actions.append(a)
        self.targets = a
        self.reward = float(reward)
        return self._report()

    def initial_command(self) -> np.ndarray:
        """A command that holds the robot where it is: zero motion, the current joints or hand poses, grip open."""
        spec, a = self.action_spec, np.zeros(self.action_dim)
        m, d = self.model, self.data
        if self.action_dim == 13:
            arm = [m.joint(f"robot0_joint{i}").qposadr[0] for i in range(1, 8)]
            a[:7] = d.qpos[arm]
        for c in spec["channels"]:
            if c["kind"] in ("grip", "mode"):
                a[c["index"]] = -1.0
        if self.action_dim == 24:
            a[:] = self._gr1_hold()
        return a

    def _gr1_hold(self) -> np.ndarray:
        """GR1: each grip site's current pose in the base frame, and hand commands at the current finger positions."""
        from scipy.spatial.transform import Rotation

        r, m, d = self.env.robots[0], self.model, self.data
        base = m.body(r.robot_model.root_body).id
        rb, pb = d.xmat[base].reshape(3, 3), d.xpos[base]
        a = np.zeros(24)
        for k, arm in enumerate(("right", "left")):
            site = m.site(f"gripper0_{arm}_grip_site").id
            a[6 * k : 6 * k + 3] = rb.T @ (d.site_xpos[site] - pb)
            a[6 * k + 3 : 6 * k + 6] = Rotation.from_matrix(rb.T @ d.site_xmat[site].reshape(3, 3)).as_rotvec()
        ctrl = np.asarray(d.ctrl, float)
        for k, arm in enumerate(("right", "left")):
            idx = r._ref_actuators_indexes_dict[f"{arm}_gripper"] if hasattr(r, "_ref_actuators_indexes_dict") else []
            if len(idx) >= 6:
                a[12 + 6 * k : 18 + 6 * k] = ctrl[list(idx)[:6]]
        return a

    def hold_targets(self) -> np.ndarray:
        """The last command with every delta / velocity channel set to zero: the robot holds still."""
        h = np.asarray(self.targets, float).copy()
        for c in self.action_spec["channels"]:
            if c["kind"] == "delta":
                h[c["index"]] = 0.0
        return h

    def replay(self, actions) -> dict:
        """Reset, then execute `actions` (T, dim): what the verifier does."""
        a = as_actions(actions, self.action_dim)
        self.reset()
        for row in a:
            self.step(row)
        return {
            "success": self.success,
            "initial_success": self.initial_success,
            "state_sha": self.state_sha(),
            "control_steps": len(a),
            "final_reward": self.reward,
        }

    def save_trajectory(self, actions=None, path="/app/output/trajectory.npz", meta: dict | None = None) -> str:
        """Write (T, dim) actions (default: those since the last reset); 1 <= T <= MAX_STEPS."""
        a = as_actions(self.actions if actions is None else actions, self.action_dim)
        if not 1 <= len(a) <= MAX_STEPS:
            raise ValueError(f"a trajectory has 1..{MAX_STEPS} actions, got {len(a)}")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, actions=a, instance_sha=np.array(self.instance_sha), meta=np.array(json.dumps(meta or {})))
        return str(path)

    # -- state -------------------------------------------------------------------------------------------------
    @property
    def model(self):
        return raw(self.env)[0]

    @property
    def data(self):
        return raw(self.env)[1]

    def check(self) -> dict:
        """The success check's last result (no extra call: the call pattern is part of the task)."""
        return self._report()

    def state_sha(self) -> str:
        return state_hash(self.env)

    def _robot_joints(self) -> list[str]:
        m = self.model
        names = [m.joint(i).name for i in range(m.njnt)]
        return [n for n in names if n.startswith(ROBOT_PREFIXES) and m.joint(n).type[0] != mujoco.mjtJoint.mjJNT_FREE]

    def _proprio_layout(self) -> list[str]:
        joints = self._robot_joints()
        arms = sorted(self.env.robots[0].eef_site_id)
        return (
            [f"{j}_pos" for j in joints]
            + [f"{j}_vel" for j in joints]
            + [f"eef_{arm}_{a}" for arm in arms for a in "xyz"]
            + [f"cmd_{n}" for n in self.action_names]
        )

    def proprio(self) -> np.ndarray:
        m, d = self.model, self.data
        joints = self._robot_joints()
        q = [d.qpos[m.joint(j).qposadr[0]] for j in joints]
        qd = [d.qvel[m.joint(j).dofadr[0]] for j in joints]
        sites = self.env.robots[0].eef_site_id
        eef = [d.site_xpos[sites[arm]] for arm in sorted(sites)]
        return np.concatenate([q, qd, *eef, self.targets]).astype(np.float32)

    def state(self) -> dict:
        """Privileged state (world frame, metres, quaternions w x y z)."""
        m, d = self.model, self.data
        bodies = {}
        for i in range(m.nbody):
            if m.body(i).name:
                bodies[m.body(i).name] = {"pos": d.xpos[i].copy(), "quat_wxyz": d.xquat[i].copy()}
        return {
            "instruction": self.inst["text"],
            "qpos": d.qpos.copy(),
            "qvel": d.qvel.copy(),
            "joint_names": [m.joint(i).name for i in range(m.njnt)],
            "bodies": bodies,
            "objects": self.meta.get("object_cfgs", []),
            "proprio": dict(zip(self.proprio_layout, self.proprio().tolist(), strict=True)),
            **self._report(),
        }

    def _report(self) -> dict:
        return {"success": self.success, "reward": self.reward, "control_steps": len(self.actions)}

    # -- rendering ---------------------------------------------------------------------------------------------
    def render(self, camera: str = "robot0_agentview_center", size: tuple[int, int] = (320, 240)) -> np.ndarray:
        w, h = size
        if (w, h) not in self._renderers:
            self._renderers[(w, h)] = mujoco.Renderer(self.model, h, w)
        r = self._renderers[(w, h)]
        cam = self.camera_views.get(camera, {"camera": camera})["camera"]
        r.update_scene(self.data, camera=cam, scene_option=scene_option())
        return r.render().copy()

    def render_grid(self, size: tuple[int, int] = (320, 240)) -> np.ndarray:
        imgs = [self.render(c, size) for c in list(self.camera_views)[:4]]
        while len(imgs) < 4:
            imgs.append(np.zeros_like(imgs[0]))
        return np.concatenate([np.concatenate(imgs[:2], 1), np.concatenate(imgs[2:4], 1)], 0)

    def render_video(self, actions, path, every: int = 2, fps: int = 10, camera: str | None = None) -> dict:
        """Reset, replay `actions` and write an mp4 (every `every`-th control step) plus <path>.last.png."""
        import imageio.v2 as imageio
        from PIL import Image

        a = as_actions(actions, self.action_dim)
        camera = camera or next(iter(self.camera_views))
        self.reset()
        frames = [self.render(camera)]
        for i, row in enumerate(a):
            self.step(row)
            if (i + 1) % every == 0 or i == len(a) - 1:
                frames.append(self.render(camera))
        with imageio.get_writer(
            str(path),
            format="FFMPEG",
            mode="I",
            fps=fps,
            codec="libx264",
            macro_block_size=1,
            output_params=["-movflags", "+faststart"],
        ) as w:
            for f in frames:
                w.append_data(f)
        Image.fromarray(frames[-1]).save(str(path).removesuffix(".mp4") + ".last.png")
        return {"frames": len(frames), "path": str(path)}

    def _close_renderers(self) -> None:
        for r in self._renderers.values():
            r.close()
        self._renderers = {}

    def close(self) -> None:
        self._close_renderers()
        if self.env is not None:
            self.env.close()
            self.env = None


def as_actions(actions, dim: int) -> np.ndarray:
    a = np.asarray(actions, dtype=np.float64)
    if a.size == 0:
        return np.zeros((0, dim))
    if a.ndim != 2 or a.shape[1] != dim:
        raise ValueError(f"actions must have shape (T, {dim}), got {list(a.shape)}")
    if not np.all(np.isfinite(a)):
        raise ValueError("actions contain NaN or inf")
    return a
