#!/usr/bin/env python3
"""Generate the RoboOlympics tasks: tasks/roboolympics-<family>-i00-privileged and -standard (eai-standard/2.1)
for every family in scripts/roboolympics/families.json (docs/benchmarks/roboolympics.md).

    python3 scripts/roboolympics/gen_tasks.py render     # (re)write every task dir; `git diff tasks/` stays empty
    python3 scripts/roboolympics/gen_tasks.py check      # write nothing; exit 1 if a task dir differs
    python3 scripts/roboolympics/gen_tasks.py render --only sprint,penalty-kick --out /tmp/x    # some families, elsewhere
Then `cd tasks && harbor add --scan .` when a digest changed. Needs only Python 3 (no simulator).

Inputs, all in the repository:
  scripts/roboolympics/families.json           per family: the seed, the oracle level, the review evidence
  scripts/roboolympics/instances/<f>-i00.json  the frozen instance + the texts and numbers the tasks quote
                                                  (make_instances.py, in the simulator image)
  scripts/roboolympics/shared/                 the tooling (rcb_rfo.py), the world package (rfo/: the core, and one
                                                  module per family under rfo/tasks/, copied as rfo_task.py), grade.py,
                                                  the sim service (standard/: the adapter server.py on rcb_service.py),
                                                  the clients, the oracle drivers (solution/)
  scripts/roboolympics/oracles/<family>/       oracle.py (privileged) and standard_rows.npz (make_oracles.py)
  scripts/roboolympics/templates/<mode>/       every other task file; *.tmpl is filled with the instance's values
  scripts/eai_standard/client.env                 the standard agent image and its pip pins
  images/robofunolympics/VERSION                  the base image tag
Every task is written to a scratch directory, passed through scripts/task_conventions.py's normalize() and synced into
tasks/: a task dir holds exactly what the generator writes."""

import argparse, json, os, pathlib, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = ROOT / "scripts/roboolympics"
SHARED = HERE / "shared"
REGISTRY = "ghcr.io/mll-lab-nu"
PREFIX = "roboolympics"
RESET_BUDGET = 50        # standard mode's attempts (PROTOCOL §4.5 per-benchmark default; owner, 2026-10-12)
RT_RESET_BUDGET = 10     # standard-realtime: PROTOCOL §4b's default (owner, 2026-10-14: every realtime task, 10 resets)
# The standard-realtime twins (PROTOCOL §4b; owner, 2026-10-14, board 0112): the families whose scene is dynamic
# (scripts/task_dynamics.toml), served by the standard twin's server.py behind the shared realtime layer
# (shared/realtime/rcb_realtime.py, HumanoidBench's, unchanged). Per family: the real-time factor RTF of that service
# with its clock flat out (RCB_SLOWDOWN = 0.01, physics only, 4 episodes; ws-1, 4 CPUs, board 0112, 2026-10-14)
# and the slowdown S it gives (PROTOCOL §4b: S = 1 when RTF >= 3, else ceil(1.5 / RTF), which is 1 for RTF >= 1.5).
RT_RTF = {"catch": 3.61, "catch-and-shoot": 3.64, "header": 3.92, "juggle-three": 3.89, "paddle-bounce": 3.74,
          "penalty-kick": 3.89, "table-tennis-return": 4.06, "tennis-return": 3.24, "trap-ball": 3.03,
          "volley-shot": 2.89, "volleyball-bump": 2.69, "volleyball-set": 2.62, "volleyball-spike": 1.83}


def slowdown_of(rtf: float) -> int:
    return 1 if rtf >= 3 else max(1, int(-(-1.5 // rtf)))
BENCHMARK = "RoboOlympics"   # the label of task_conventions.BENCHMARKS
# The agent's time cutoff per mode (PROTOCOL §2.12): this benchmark's own number, written into every task's `[agent]
# timeout_sec`, the one source; normalize renders from it the instruction's closing `## Time limit`, the README row and
# the sim service's wall clock. To change it (an owner decision; the pull request states old -> new), edit it here and
# regenerate.
CUTOFF_SEC = 7200   # the same in both modes (PROTOCOL §2.15); the exported tasks (exported.toml) keep their own


def agent_timeout() -> int:
    """The agent's time limit (PROTOCOL §2.12), the same in both modes; the templates never state it as a number."""
    return CUTOFF_SEC
CORE = ("__init__.py", "scene.py", "looks.py", "world.py", "referee.py", "task.py")   # the rfo package in a task (no other family)
MODES = ("privileged", "standard")
CLIENT = dict(
    line.split("=", 1)
    for line in (ROOT / "scripts/eai_standard/client.env").read_text().splitlines()
    if "=" in line and not line.startswith("#")
)
SHORT = {  # the action types' rows, in words (the layout itself is in instance.json / spec()); {w} waist joints, {n} joints
    "stand": "waist {w} + arms 14 joint targets",
    "walk": "`vx`, `vy`, `wz` + waist {w} + arms 14 joint targets",
    "walk_falcon": "`vx`, `vy`, `wz` + waist {w} + arms 14 joint targets (as `walk`)",
    "walk_agile": "`vx`, `vy`, `wz` + waist {w} + arms 14 joint targets (as `walk`)",
    "run": "`vx`, `vy`, `wz`",
    "run_arms": "`vx`, `vy`, `wz` + arms 14 joint targets",
    "joints": "all {n} joint targets",
    "lowcmd": "all {n} joints × (`q`, `dq`, `tau`, `kp`, `kd`): {n} targets, then {n} velocities, {n} torques, {n} kp, {n} kd",
}
NOTE_STAND = """- **`stand`** holds the legs at the standing pose with stiff gains and a gravity-support torque. It is not a balance
  controller: it does not step and it has no feedback. After an arm movement the body sways a few centimetres for a
  few seconds; a hard or fast swing of the arms, a push or a load can tip the robot over within a second or two."""
NOTE_WALK = {
    "unitree_g1": """- **`walk`** runs Unitree's own G1 walking policy (50 Hz) on the legs. At the largest forward command (0.8) it walks at
  about 0.6 m/s; `vy` up to 0.5 and `wz` up to 1.57 rad/s; it follows with lag and barely moves in its first second.
  At a zero command it marks time on the spot (the pelvis sways and drifts a centimetre or two per second) and
  recovers from small disturbances, which `stand` does not. When the legs come to it from another mode it first blends
  them to the stance (0.3 s) and holds a zero command until the robot is steady (up to 2 s). It was trained with the
  arms at rest: moving the arms and the waist disturbs it.""",
    "unitree_h1": """- **`walk`** runs Unitree's own H1-2 walking policy (50 Hz) on the legs. At the largest forward command (0.8) it walks at
  about 0.6 m/s and its heading drifts (close the loop on the IMU); `vy` up to 0.5 and `wz` up to 1.57 rad/s. At a
  zero command it marks time on the spot and recovers from small disturbances, which `stand` does not. When the legs
  come to it from another mode it first blends them to the stance (0.3 s) and holds a zero command until the robot is
  steady (up to 2 s). It was trained with the arms at their zero pose (upper arms down, forearms forward): moving the
  arms disturbs it. This robot has no running policy: anything faster than a walk is yours to build or to find. The
  G1's two other walking policies (FALCON, AGILE) are not offered for it: driven on this robot (joints matched by name)
  they keep it upright but do not walk it.""",
}
NOTE_WALKERS = """- **`walk_falcon`** and **`walk_agile`** are two more walking policies for the G1's legs, with the same row as `walk`
  (you keep the waist and the arms): FALCON (LeCAR-Lab, MIT; trained with arm motions and forces on the hands) and
  AGILE's velocity-height policy (NVIDIA WBC-AGILE, Apache-2.0; trained while the arms and the waist moved), the
  released weights run in numpy at 50 Hz on their own leg gains (kp 100 / 100 / 100 / 200 / 20 / 20 per leg). Both
  hold still and follow the command better than `walk` while the arms move or carry something; FALCON also adds a small
  correction to the wrists. FALCON zeroes speeds below 0.2 m/s and turns below 0.2 rad/s and stands with the pelvis at
  about 0.74 m; AGILE zeroes commands of norm below 0.1, stands lower (about 0.68 m) and barely turns on the spot below
  about 0.7 rad/s (walking at 0.2 m/s or more it turns as asked). Their command ranges are in the action table. A
  walker takes the legs at once, from where they are (its memory starts afresh); `walk`, the other walker and `run`
  take them from it the same way. Going from a walker straight to `stand` usually ends in a fall (`stand` holds
  Unitree's stance and does not balance): give `walk` a zero command for about 2 s first."""
NOTE_RUN = """- **`run`** runs RoboOlympics' athletics running policy (50 Hz) on all 29 joints: `vx` from 0 to about 4 m/s (it falls
  above that; the command changes at most 1.5 m/s per second), `|vy|` ≤ 0.12 m/s, `|wz|` ≤ 0.5 rad/s. `run_arms` gives
  you the arms while it keeps the legs and the waist; taking the arms away from its swing disturbs it. Switching to
  `stand`, `walk` or `joints` above about 0.6 m/s usually ends in a fall: slow down first (from 2.4 m/s that takes
  about 2 s and 2.3 m)."""
NOTE_REST = """- **`joints` / `lowcmd`** are yours: each motor's torque is `kp (q − q_measured) + kd (dq − dq_measured) + tau`, evaluated
  at 1 kHz with your row held for its 10 ms, then limited by the motor's torque-speed curve and torque limit. `joints`
  uses the default gains of the table and zero `dq` and `tau`; `lowcmd` takes yours (kp up to @@KP_MAX@@ and kd up to
  @@KD_MAX@@ for legs / waist / arms). Nothing balances the robot in these modes but your own targets.
- **Every joint target** is clipped into the joint's range and moves at most the joint's speed limit × 10 ms per step
  from the target in force. Joints a type does not name keep their targets. The speed limit is a limit on targets;
  what bounds the joint itself is the motor's torque-speed curve (a `lowcmd` feed-forward torque can turn a joint up to
  about 1.15 times that speed, where the motor's torque has fallen to zero).
- **The hands** have no working fingers here; each carries a fist pad (a box of 4.4 × 8 × 10 cm beyond the wrist, the
  10 cm along the forearm) with a grip: while `grip_left` / `grip_right` ≥ 0.5 the hand holds the nearest grippable
  object whose surface is within 3.5 cm of the palm point (the middle of the pad, 4.5 cm beyond the wrist flange along
  the forearm) and that moves at most 6 m/s relative to it; below 0.5 it lets go at once. Since the palm point is inside
  the pad, an object can be gripped where it touches one of the pad's two broad faces, not at its narrow sides or its
  far end. What is grippable is the task's own equipment, named in the rules.
- **A tool on a hand** (a racket, a paddle, a club; where the task has one) is fixed to the wrist in place of the pad.
  It collides with the world, the ball and the rest of your own body.
- **The air** is real: balls and implements feel drag and, when they spin, lift.
- **If the physics diverges** (a numerical blow-up, typically from a violent joint command), the attempt ends as a
  failure: "the simulation became unstable"."""


def control_notes(t0: dict) -> str:
    r = t0["robot"]
    name = r.get("name", "unitree_g1")
    caps = lambda k: " / ".join(f"{r[k][i]:g}" for i in (0, 12, len(r[k]) - 1))  # noqa: E731 -- legs / waist / arms
    parts = [NOTE_STAND, NOTE_WALK[name]] + ([NOTE_WALKERS] if "walk_falcon" in t0["action_types"] else []) + (
        [NOTE_RUN] if r.get("run_command_range") else [])
    parts.append(NOTE_REST.replace("@@KP_MAX@@", caps("kp_max")).replace("@@KD_MAX@@", caps("kd_max")))
    return "What the platform does and does not do for you:\n\n" + "\n".join(parts)


def rulebook_block(inst: dict) -> str:
    if not inst.get("rulebook"):
        return ""
    out = f"**Rule book:** {inst['rulebook']}."
    if inst.get("deviations"):
        out += " Where this task departs from it:\n\n" + "\n".join(f"- {d}" for d in inst["deviations"])
    else:
        out += " This task departs from it in nothing that the referee judges."
    return out + "\n\n"



def dynamic_families() -> dict[str, str]:
    """{family: why} of the families scripts/task_dynamics.toml marks dynamic (their `[metadata] family` is fam_id)."""
    import tomllib
    t = tomllib.loads((ROOT / "scripts/task_dynamics.toml").read_text())
    row = t["benchmark"][BENCHMARK]
    return {f.replace("_", "-"): e["why"] for f, e in t.get("family", {}).get(BENCHMARK, {}).items()
            if e["dynamics"] == "dynamic" and row["dynamics"] != "dynamic"}


def task_dir(fam: str, mode: str) -> str:
    return f"{PREFIX}-{fam}-i00-{mode}"


def fill(text: str, values: dict) -> str:
    for k, v in values.items():
        text = text.replace(f"@@{k}@@", str(v))
    if "@@" in text:
        raise RuntimeError(f"unfilled placeholder near {text[text.index('@@'):][:40]!r}")
    return text


def toml_str(text: str) -> str:
    """The inside of a basic TOML string."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def walkers(t0: dict) -> str:
    out = ""
    for name in ("walk_falcon", "walk_agile"):
        t = t0["action_types"].get(name)
        if t:
            lo, hi = t["lower"][:3], t["upper"][:3]
            out += (f"; `{name}` {lo[0]:g} ≤ vx ≤ {hi[0]:g}, {lo[1]:g} ≤ vy ≤ {hi[1]:g}, {lo[2]:g} ≤ wz ≤ {hi[2]:g}")
    return out


def action_table(t0: dict, mode: str) -> str:
    rows = ["| type | row (then `grip_left`, `grip_right`) | floats | who drives what |", "|---|---|---|---|"]
    n = len(t0["robot"]["joints"])
    for name, t in t0["action_types"].items():
        rows.append(f"| `{name}` | {SHORT[name].format(w=n - 26, n=n)} | {t['dim']} | {t['meaning']} |")
    walk, run = t0["robot"]["walk_command_max"], t0["robot"].get("run_command_range")
    runs = (f"; `run` and `run_arms` {run[0][0]:g} ≤ vx ≤ {run[0][1]:g}, |vy| ≤ {run[1][1]:g}, |wz| ≤ {run[2][1]:g}"
            if run else "")
    return "\n".join(rows) + (
        f"\n\nVelocity commands are in the robot's own frame (`vx` forward, `vy` to its left, m/s; `wz` turning left, "
        f"rad/s). Bounds: `walk` |vx| ≤ {walk[0]:g}, |vy| ≤ {walk[1]:g}, |wz| ≤ {walk[2]:g}{walkers(t0)}{runs}. Joint targets are absolute "
        "angles (rad). Values outside the bounds are clipped. `grip_left`, `grip_right`: ≥ 0.5 closes the hand's grip, "
        "< 0.5 opens it. " + (
            start_note(t0, mode)))


def start_row(t0: dict) -> list:
    """The joint targets in force at t = 0, one per joint (the instance's hold row; the legs' stance in `stand`)."""
    r, h = t0["robot"], t0["hold"]
    n = len(r["joints"])
    if h["type"] == "stand":
        return list(r["stance_legs_rad"]) + list(h["row"][:-2])
    if h["type"] in ("joints", "lowcmd"):
        return list(h["row"][:n])
    return list(r["stance_legs_rad"]) + list(h["row"][3:-2])     # walk, run_arms: a velocity command, then the upper body


def start_note(t0: dict, mode: str) -> str:
    r, h = t0["robot"], t0["hold"]
    row = "[" + ", ".join(f"{x:g}" for x in h["row"]) + "]"
    where = ("`s.hold()` returns it" if mode == "privileged" else
             "`spec()[\"start_command\"]` has it, and `get_obs(seconds=...)` keeps the command in force")
    grips = [side for side, g in zip(("left", "right"), h["row"][-2:]) if g >= 0.5]
    held = f" The {' and the '.join(grips)} grip{'s are' if len(grips) > 1 else ' is'} closed at the start." if grips else ""
    if h["type"] == "stand":
        rest = list(r["rest_upper_rad"])
        if max(abs(a - b) for a, b in zip(h["row"][:-2], rest)) < 1e-3 and not grips:
            return ("At the start the robot stands in `stand` mode with the arms at rest: the `stand` row with the "
                    "table's start angles and both grips open keeps it there.")
        return ("At the start the robot is in `stand` mode, but not with the arms at rest (the venue text says how it "
                "starts): the joint table's last column has the angles in force." + held + " The `stand` row that "
                f"keeps the start as it is: `{row}` ({where}); a `stand` row with other angles or grips moves the "
                "arms or lets go.")
    return (f"At the start the robot is not in the plain standing pose (the venue text says how it starts): it is held "
            f"in `{h['type']}` mode." + held + f" The row that keeps the command in force: {where}.")


def joint_table(t0: dict) -> str:
    r = t0["robot"]
    rest = start_row(t0)
    assert len(rest) == len(r["joints"]), (len(rest), len(r["joints"]), t0["hold"]["type"])
    rows = ["| # | joint | range (rad) | speed (rad/s) | torque (N m) | kp | kd | at the start (rad) |", "|---|---|---|---|---|---|---|---|"]
    for i, j in enumerate(r["joints"]):
        lo, hi = r["range_rad"][i]
        rows.append(f"| {i} | `{j}` | [{lo:g}, {hi:g}] | {r['speed_limit_rad_s'][i]:g} | {r['torque_limit_nm'][i]:g} | "
                    f"{r['default_kp'][i]:g} | {r['default_kd'][i]:g} | {rest[i]:g} |")
    return "\n".join(rows)


def values(fam: str, spec: dict, inst: dict, version: str) -> dict:
    t0, texts = inst["t0"], inst["texts"]
    rob = t0["robot"]
    sentence = texts["sentence"]
    full = spec["oracle"] == "full"
    measured = measured_std = ""
    if full:      # what make_oracles.py measured when it recorded the reference solution
        res = json.loads((HERE / "oracles" / fam / "result.json").read_text())
        measured = (f" Measured (make_oracles.py): success after {res['time_s']:g} s of the {res['time_limit_s']:g} s "
                    "limit, live and in a fresh replay, ending in the same state.")
        measured_std = (f" The privileged twin's reference rows ({res['steps']} control steps, success after "
                        f"{res['time_s']:g} s) streamed through the client.")
    test = f"scripts/roboolympics/tests/test_{fam.replace('-', '_')}.py"
    review = spec.get("review", "")
    none_ev = ("no reference solution; the referee is tested by " + test + ": " + spec["evidence"] + "; human review "
               + (f"in PR #{review}" if review else "in the pull request that adds the benchmark") + " (PROTOCOL §2.7)")
    return {
        "FAMILY": fam,
        "FAMILY_ID": fam.replace("-", "_"),
        "CATEGORY": inst["category"],
        "TITLE": inst["title"],
        "SEED": inst["seed"],
        "SENTENCE": sentence,
        "SENTENCE_TOML": toml_str(sentence),
        "VENUE": texts["venue"],
        "RULES": texts["rules"],
        "DIFFICULTY": texts["difficulty"],
        "START_NOTE": "",
        "STAGES": " → ".join(inst["stages"]),
        "HORIZON_STEPS": t0["horizon_steps"],
        "HORIZON_S": f"{inst['time_limit_s']:g}",
        "RAW_DIM": t0["raw_dim"],
        "CAMERAS": ", ".join(f"`{c}`" for c in t0["cameras"]),
        "ACTION_TABLE": action_table(t0, "privileged"),
        "ACTION_TABLE_STD": action_table(t0, "standard"),
        "VENUE_CAMERAS": ", ".join(f"`{c}`" for c in t0["cameras"] if not c.startswith("head_")),
        "WALK_DIM": t0["action_types"]["walk"]["dim"],
        "ROBOT_SHORT": {"unitree_g1": "G1", "unitree_h1": "H1-2"}[rob["name"]],
        "JOINT_TABLE": joint_table(t0),
        "CONTROL_NOTES": control_notes(t0),
        "RULEBOOK": rulebook_block(inst),
        "RULEBOOK_ROW": ((inst.get("rulebook") or "none (not a rule-book event)") + (
            "; deviations: " + " · ".join(inst["deviations"]) if inst.get("deviations") else "")).replace("|", "/"),
        "ROBOT_LINE": (f"{rob['title']} humanoid robot ({len(rob['joints'])} joints, {rob['height_m']:g} m tall, "
                       f"{rob['mass_kg']:.0f} kg; the RoboOlympics simulator on MuJoCo)"),
        "ROBOT_TITLE": rob["title"], "ROBOT_ID": {"unitree_g1": "unitree-g1", "unitree_h1": "unitree-h1-2"}[rob["name"]],
        "ROBOT_KW": {"unitree_g1": "unitree-g1", "unitree_h1": "unitree-h1-2"}[rob["name"]],
        "NJ": len(rob["joints"]),
        "AGENT_TIMEOUT": agent_timeout(),
        "RESET_BUDGET": RESET_BUDGET,
        "PRIV": task_dir(fam, "privileged"),
        "STD": task_dir(fam, "standard"),
        "SHA": t0["state_sha"],
        "IMAGE": f"{REGISTRY}/eai-robofunolympics:{version}",
        "CLIENT_IMAGE": CLIENT["CLIENT_IMAGE"].strip(),
        "EXPERT_HOURS": spec.get("expert_hours", 3.0),
        "EXPERT_HOURS_STD": spec.get("expert_hours_standard", spec.get("expert_hours", 3.0) + 2.0),
        "ORACLE": spec["oracle"],
        "ORACLE_EVIDENCE": toml_str(spec["evidence"] + measured if full else none_ev),
        "ORACLE_EVIDENCE_STD": toml_str(spec["evidence"] + measured_std if full else none_ev),
        "REFERENCE": (
            "`solution/oracle.py` drives the robot through the task's own tooling, closed loop on the privileged state, "
            "and writes the trajectory (`solution/solve.sh`). " + spec["evidence"] + measured) if full else (
            "None. No reference controller exists for this family yet: " + spec["evidence"] + "."),
        "REFERENCE_STD": (
            "`solution/oracle_replay.py` streams the privileged twin's reference solution, row by row, through the "
            "client (`solution/rows.npz`, recorded by scripts/roboolympics/make_oracles.py). "
            + spec["evidence"] + measured_std) if full else f"None (as `{task_dir(fam, 'privileged')}`).",
        "RT": task_dir(fam, "standard-realtime"),
        "RT_RESET_BUDGET": RT_RESET_BUDGET,
        "EXPERT_HOURS_RT": spec.get("expert_hours", 3.0) + 4.0,
        "ORACLE_EVIDENCE_RT": toml_str(
            spec["evidence"] + " In standard-realtime mode the privileged twin's reference rows, each run of one action "
            "type planned at the control step where it ran (`submit(..., at=step)`), succeed at the task's S (board "
            "0112)." if full else none_ev),
        "REFERENCE_RT": (
            "`solution/oracle_plan.py` plans the privileged twin's reference rows (`solution/rows.npz`) into the attempt "
            "at the control steps where they ran there (`submit(..., at=step)`; the first, at step 0, starts the clock); "
            "it uses no privileged information at run time. " + spec["evidence"]) if full else (
            f"None (as `{task_dir(fam, 'privileged')}`)."),
        "REVIEW": "" if full else ("No oracle; human review " + (f"in PR #{review}" if review else
                                   "in the pull request that adds the benchmark") + " (PROTOCOL §2.7)."),
    }


def files_of(tdir: pathlib.Path, vals: dict) -> dict[str, tuple[bytes, int]]:
    out = {}
    for p in sorted(tdir.rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        rel = p.relative_to(tdir).as_posix()
        if rel.endswith(".tmpl"):
            rel, data = rel[:-5], fill(p.read_text(), vals).encode()
        else:
            data = p.read_bytes()
        out[rel] = (data, 0o755 if rel.endswith(".sh") else 0o644)
    return out


def world_files(fam: str, base: str) -> dict[str, tuple[bytes, int]]:
    """The tooling, the rfo package's core and this family's rules under `base` (environment, tests, environment/sim)."""
    out = {f"{base}/rcb_rfo.py": ((SHARED / "rcb_rfo.py").read_bytes(), 0o644),
           f"{base}/rfo_task.py": ((SHARED / "rfo/tasks" / f"{fam.replace('-', '_')}.py").read_bytes(), 0o644)}
    for name in CORE:
        out[f"{base}/rfo/{name}"] = ((SHARED / "rfo" / name).read_bytes(), 0o644)
    return out


def plan(fam: str, spec: dict, version: str) -> dict[str, dict[str, tuple[bytes, int]]]:
    """{task dir name: {relative path: (content, mode)}} for the modes of one family (standard-realtime: dynamic ones)."""
    path = HERE / "instances" / f"{fam}-i00.json"
    raw = path.read_bytes()
    inst = json.loads(raw)
    if inst["family"] != fam or inst["seed"] != spec.get("seed", 0):
        raise RuntimeError(f"{path.name} does not match families.json (family, seed)")
    vals = values(fam, spec, inst, version)
    std, sol, orc = SHARED / "standard", SHARED / "solution", HERE / "oracles" / fam
    full = spec["oracle"] == "full"
    out = {}
    dyn = dynamic_families()
    modes = MODES + (("standard-realtime",) if fam in dyn else ())
    for mode in modes:
        if mode == "privileged":
            files = files_of(HERE / "templates/privileged", vals)
            files.update(world_files(fam, "environment"))
            files.update(world_files(fam, "tests"))
            for rel in ("environment/instance.json", "tests/instance.json"):
                files[rel] = (raw, 0o644)
            files["tests/grade.py"] = ((SHARED / "grade.py").read_bytes(), 0o644)
            if full:
                files["solution/solve.sh"] = ((sol / "solve_privileged.sh").read_bytes(), 0o755)
                files["solution/run_oracle.py"] = ((sol / "run_oracle.py").read_bytes(), 0o644)
                files["solution/oracle.py"] = ((orc / "oracle.py").read_bytes(), 0o644)
        else:
            rt = mode == "standard-realtime"
            v = dict(vals, REFERENCE=vals["REFERENCE_RT" if rt else "REFERENCE_STD"], ACTION_TABLE=vals["ACTION_TABLE_STD"])
            if rt:
                S = slowdown_of(RT_RTF[fam])
                v.update(SLOWDOWN=S, REAL_TIME_NOTE=" (real time)" if S == 1 else "", DYNAMIC_WHY=dyn[fam],
                         RTF_TEXT=(f"RTF {RT_RTF[fam]:g} with the clock flat out (RCB_SLOWDOWN = 0.01, physics only, 4 "
                                   "attempts; ws-1, 4 CPUs, board 0112, 2026-10-14); PROTOCOL §4b: S = 1 when RTF "
                                   ">= 3, else ceil(1.5 / RTF)"))
            files = files_of(HERE / ("templates/standard-realtime" if rt else "templates/standard"), v)
            files["environment/rcb_client.py"] = (((SHARED / "realtime") if rt else std).joinpath("rcb_client.py").read_bytes(), 0o644)
            if rt:
                files["environment/sim/rcb_realtime.py"] = ((SHARED / "realtime/rcb_realtime.py").read_bytes(), 0o644)
            files["environment/rcb1.py"] = ((std / "rcb1.py").read_bytes(), 0o644)
            req = CLIENT["CLIENT_REQUIREMENTS"].strip()
            files["environment/client-requirements.txt"] = ((ROOT / "scripts/eai_standard" / req).read_bytes(), 0o644)
            for name in ("server.py", "rcb_service.py", "rcb1.py"):
                files[f"environment/sim/{name}"] = ((std / name).read_bytes(), 0o644)
            files.update(world_files(fam, "environment/sim"))
            files["environment/sim/instance.json"] = (raw, 0o644)
            files["tests/grade.py"] = ((std / "grade.py").read_bytes(), 0o644)
            if full and rt:
                files["solution/solve.sh"] = ((sol / "solve_realtime.sh").read_bytes(), 0o755)
                files["solution/oracle_plan.py"] = ((sol / "oracle_plan.py").read_bytes(), 0o644)
                files["solution/rows.npz"] = ((orc / "standard_rows.npz").read_bytes(), 0o644)
            elif full:
                files["solution/solve.sh"] = ((sol / "solve_standard.sh").read_bytes(), 0o755)
                files["solution/oracle_replay.py"] = ((sol / "oracle_replay.py").read_bytes(), 0o644)
                files["solution/rows.npz"] = ((orc / "standard_rows.npz").read_bytes(), 0o644)
        out[task_dir(fam, mode)] = files
    return out


def normalized(planned: dict, normalize) -> dict:
    """Write the tasks to a scratch tasks/ dir, run task_conventions.normalize() on each and read them back."""
    out = {}
    with tempfile.TemporaryDirectory(prefix="robofun_gen_") as td:
        for name, files in planned.items():
            for rel, (data, mode) in files.items():
                p = pathlib.Path(td) / name / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
                os.chmod(p, 0o755 if mode & 0o100 else 0o644)
        for name in planned:
            normalize(pathlib.Path(td) / name)
        for name in planned:
            t = pathlib.Path(td) / name
            out[name] = {
                p.relative_to(t).as_posix(): (p.read_bytes(), 0o755 if p.stat().st_mode & 0o100 else 0o644)
                for p in sorted(t.rglob("*"))
                if p.is_file() and "__pycache__" not in p.parts
            }
    return out


def sync(task: pathlib.Path, files: dict, check: bool) -> list[str]:
    """Make `task` hold exactly `files`. Returns the differences (written unless check)."""
    diffs = []
    have = {p.relative_to(task).as_posix() for p in task.rglob("*") if p.is_file() or p.is_symlink()} if task.exists() else set()
    have = {h for h in have if "__pycache__" not in h.split("/")}
    for rel in sorted(have - set(files)):
        diffs.append(f"remove {task.name}/{rel}")
        if not check:
            (task / rel).unlink()
    for rel, (data, mode) in sorted(files.items()):
        p = task / rel
        same = p.is_file() and not p.is_symlink() and p.read_bytes() == data and bool(p.stat().st_mode & 0o100) == bool(mode & 0o100)
        if not same:
            diffs.append(f"write  {task.name}/{rel}")
            if not check:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
                os.chmod(p, 0o755 if mode & 0o100 else 0o644)
    if not check and task.exists():
        for d in sorted((p for p in task.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
            if not any(d.iterdir()):
                d.rmdir()
    return diffs


def exported_names() -> set[str]:
    """The task directories RoboOlympics exports itself (exported.toml, written by its tools/export_fexam.py): its own
    service unchanged inside the task (docs/benchmarks/roboolympics.md, "Tasks exported by RoboOlympics"); not rendered
    here. Their names never take a family name of this generator (the sport's id and a format: tabletennis-match,
    badminton-actskill; the families here are dashed event names: table-tennis-return)."""
    p = HERE / "exported.toml"
    if not p.is_file():
        return set()
    import tomllib
    return {t["name"] for t in tomllib.loads(p.read_text()).get("tasks", [])}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("render", "check"))
    ap.add_argument("--only", default="", help="comma-separated families (default: all)")
    ap.add_argument("--out", default=str(ROOT / "tasks"), help="the tasks directory to write (default: tasks/)")
    a = ap.parse_args()
    check = a.cmd == "check"
    os.umask(0o022)
    fams = json.loads((HERE / "families.json").read_text())["families"]
    only = [f for f in a.only.split(",") if f]
    if unknown := sorted(set(only) - set(fams)):
        raise SystemExit(f"unknown families: {unknown}")
    version = (ROOT / "images/robofunolympics/VERSION").read_text().strip()
    sys.path.insert(0, str(ROOT / "scripts"))
    from task_conventions import normalize

    out = pathlib.Path(a.out)
    diffs, made = [], set()
    for fam, spec in fams.items():
        if only and fam not in only:
            continue
        for name, files in normalized(plan(fam, spec, version), normalize).items():
            made.add(name)
            diffs += sync(out / name, files, check)
    if not only:
        exported = exported_names()      # written by RoboOlympics' own exporter (exported.toml), not by this generator
        for t in sorted(out.glob(f"{PREFIX}-*")):
            if t.is_dir() and t.name not in made and t.name not in exported:
                diffs.append(f"stale  {t.name} (no family for it: remove it)")
        diffs += [f"clash  {n}: rendered here and listed in exported.toml" for n in sorted(made & exported)]
        if out.resolve() == (ROOT / "tasks").resolve():
            diffs += [f"missing {n}: listed in exported.toml, no task directory" for n in sorted(exported)
                      if not (out / n / "task.toml").is_file()]
    for d in diffs:
        print(d)
    print(f"{'checked' if check else 'generated'} {len(made)} RoboOlympics task dirs ({len(fams)} families): {len(diffs)} difference(s)")
    return 1 if (check and diffs) else 0


if __name__ == "__main__":
    sys.exit(main())
