#!/usr/bin/env python3
"""Generate the Panda Dynamic Scenes tasks: tasks/pandadyn-<code>-<name>-iNN-privileged and -standard (eai-standard/2.2) for
every frozen instance in scripts/pandadyn/instances.json, and -standard-realtime (eai-standard/2.3) for the dynamic families
in REALTIME (docs/benchmarks/pandadyn.md).

    python3 scripts/pandadyn/mk_tasks.py              # (re)write every Panda Dynamic Scenes task dir; `git diff tasks/` stays empty
    python3 scripts/pandadyn/mk_tasks.py --check      # write nothing; exit 1 if a task dir differs from the generator's
Then `cd tasks && harbor add --scan .` when a digest changed. Needs only Python 3 (no simulator).

Inputs, all in the repository:
  scripts/pandadyn/instances.json          per task: the frozen instance (id NN = task iNN), its hashes and its provenance
                                           (scripts/pandadyn/freeze.py writes it)
  scripts/pandadyn/frozen/<task>-iNN/      instance.json (the task, its nominal parameters, its seed, the start's state hash)
                                           and oracle_actions.npy (the reference rows, one per control step, up to the success)
  scripts/pandadyn/descr/<code>.json       what the task asks and exactly what its check tests, written from the task's code
                                           (scene: what both modes may read; scene_privileged: privileged mode only)
  scripts/pandadyn/shared/rcb_pandadyn.py  the tooling (privileged environment/ + tests/, standard environment/sim/)
  scripts/pandadyn/template/<mode>/        every other task file; a *.tmpl file is filled with the instance's values (@@KEY@@)
  scripts/eai_standard/                    the eai-standard/2.2 layer, copied unchanged, and the standard client (client.env)
  scripts/humanoidbench/shared/            the eai-standard/2.3 realtime layer (realtime/rcb_realtime.py, rcb_client.py;
                                           standard/rcb_service.py, grade.py), copied unchanged into the standard-realtime twins
  images/pandadyn/                         VERSION (the base image tag) and the environment package (the servo fractions
                                           of each task are read from its source)
Both twins of an instance are written to a scratch directory, passed through scripts/task_conventions.py's normalize() and
then synced into tasks/: a task dir holds exactly what the generator writes."""
from __future__ import annotations
import argparse, json, os, pathlib, re, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = ROOT / "scripts/pandadyn"
LAYER = ROOT / "scripts/eai_standard"
PKG = ROOT / "images/pandadyn/panda_dynamics"
REGISTRY = "ghcr.io/mll-lab-nu"
CLIENT = dict(l.split("=", 1) for l in (LAYER / "client.env").read_text().splitlines() if "=" in l and not l.startswith("#"))
MAX_ROWS = 4500
RT_LAYER = ROOT / "scripts/humanoidbench/shared"     # the shared eai-standard/2.3 layer (one source; check-tooling-identity.sh)
# The standard-realtime twins (owner, 2026-10-14, board 0107 E3 / board 0112): the dynamic families (each task's `[metadata] dynamics`;
# PROTOCOL §2.14), each with its slowdown S from the real-time factor RTF of its realtime service, measured on the reference
# workstation (docs/benchmarks/pandadyn.md "Standard-realtime": the realtime service with its clock flat out, RCB_SLOWDOWN =
# 0.01, and the bare physics loop, at host loads 18-80): S = 1 when RTF >= 3, else ceil(1.5 / RTF) with the lowest RTF
# measured (PROTOCOL §4b). code -> (RTF range as measured, S)
REALTIME = {
    "D01": ("0.69-1.00", 3), "D02": ("0.52-0.83", 3), "D03": ("0.71-1.01", 3), "D04": ("0.42-0.75", 4),
    "D06": ("0.73-0.94", 3), "D07": ("0.51-0.87", 3), "D09": ("0.61-0.98", 3), "D10": ("0.30-0.55", 6),
    "S01": ("1.22-1.49", 2), "S02": ("1.24-1.41", 2), "S03": ("1.18-1.21", 2), "S04": ("1.02-1.06", 2),
    "S05": ("1.20-1.21", 2), "S07": ("0.46-0.48", 4), "S08": ("0.29", 6), "S09": ("0.92-1.14", 2),
    "S10": ("0.84", 2), "S11": ("0.69-0.94", 3), "S12": ("0.68", 3),
}
RT_RESETS = 10        # PROTOCOL §4b: every standard-realtime task allows resets, 10 by default (owner, 2026-10-14)
POSITION_IN_TEXT = re.compile(r"\(\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*\)")


def toml_str(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def kebab(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


def base(task: str, i: int) -> str:
    code, name = task.split("-", 1)
    return f"pandadyn-{code.lower()}-{kebab(name)}-i{i:02d}"


def normalizer():
    sys.path.insert(0, str(ROOT / "scripts"))
    from task_conventions import normalize
    return normalize


# The agent's time cutoff per mode (PROTOCOL §2.12): this benchmark's own number, written into every task's `[agent]
# timeout_sec`, the one source; normalize renders from it the instruction's closing `## Time limit`, the README row and
# the sim service's wall clock. To change it (an owner decision; the pull request states old -> new), edit it here and
# regenerate.
CUTOFF_SEC = {"privileged": 3600, "standard": 3600, "standard-realtime": 3600}


def agent_timeout(mode: str) -> int:
    return CUTOFF_SEC[mode]


def fill(text: str, values: dict) -> str:
    for k, v in values.items():
        text = text.replace(f"@@{k}@@", v)
    if "@@" in text:
        raise RuntimeError(f"unfilled placeholder near {text[text.index('@@'):][:40]!r}")
    return text


def servo_fractions(module: str) -> tuple[float, float]:
    """The task's reference acceleration and jerk fractions (class attributes; base_env's defaults otherwise)."""
    src = (PKG / "tasks" / (module.replace(".", "/") + ".py")).read_text()
    acc = re.search(r"^\s*REFERENCE_ACCELERATION\s*=\s*([0-9.]+)", src, re.M)
    jerk = re.search(r"^\s*REFERENCE_JERK\s*=\s*([0-9.]+)", src, re.M)
    return float(acc.group(1)) if acc else 0.55, float(jerk.group(1)) if jerk else 0.05


def module_of(code: str) -> str:
    src = (PKG / "manifest.py").read_text()
    m = re.search(rf'"{code}",\s*"[^"]+",\s*"[^"]*",\s*"([a-z_.]+)"', src)
    if not m:
        raise RuntimeError(f"manifest.py has no module for {code}")
    return m.group(1)


# Standard mode's texts (STANDARD_MODE.md §10 as this benchmark declares it, docs/benchmarks/pandadyn.md, D7): the task's
# goal geometry stays, the privileged tooling's names and the scene's physical parameters go. STD_SUB rewrites the
# descriptions' wording for standard mode; STD_FORBIDDEN must not survive it.
STD_SUB = [
    (r"\s*\(half of `fixture_speed`\)", ""),
    (r"(?:[\d.]+ x )?`(?:friction|incoming_speed|fixture_speed)`(?: x g)? = ", ""),
    (r" with a fixed impulse \(`disturbance_impulse`\)", " with a fixed impulse"),
    (r"at least 95% of `disturbance_impulse`", "at least 95% of it"),
    (r"(?:^|(?<=\. ))[^.]*(?:no phase condition uses it|no predicate uses it|not exported as a goal_\* observation)[^.]*\.\s*", ""),
    (r",? (?:and )?(?:it is |are |is )?announced (?:at reset )?(?:in the (?:observation|state) )?as `goal_\w+`(?: = \([^)]*\))?", ""),
    (r"\s*\((?:announced (?:at reset )?as `goal_\w+`)\)", ""),
    (r"\. It is announced at reset as `goal_\w+` = \([^)]*\)", ""),
    (r"; its coordinates are announced as `goal_goal`, see privileged details", ""),
    (r"; coordinates in privileged details", ""),
    (r", given in flag `passages` \(not announced in the observation\)", ""),
]
STD_FORBIDDEN = re.compile(r"`goal_|privileged|`friction`|incoming_speed|fixture_speed|disturbance_impulse|\bseed\b|\bflag", re.I)


def std_text(text: str, where: str) -> str:
    for pat, new in STD_SUB:
        text = re.sub(pat, new, text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    m = STD_FORBIDDEN.search(text)
    if m:
        raise RuntimeError(f"{where}: standard-mode text still says {m.group(0)!r}: ...{text[max(0, m.start() - 80):m.end() + 40]}...")
    return text


def num(v) -> str:
    return f"{v:g}" if isinstance(v, float) else str(v)


def plan_instance(task: str, R: dict, version: str) -> dict[str, dict[str, tuple[bytes, int]]]:
    i = int(R["id"])
    code = task.split("-", 1)[0]
    D = json.loads((HERE / "descr" / f"{code}.json").read_text())
    if D["task"] != task:
        raise RuntimeError(f"descr/{code}.json is for {D['task']}")
    fz = HERE / "frozen" / f"{task}-i{i:02d}"
    inst_b = (fz / "instance.json").read_bytes(); I = json.loads(inst_b)
    oracle_b = (fz / "oracle_actions.npy").read_bytes()
    if I.get("task") != task or I.get("initial_sha") != R["initial_sha"] or int(I["seed"]) != int(R["seed"]):
        raise RuntimeError(f"{fz}: instance.json does not match instances.json (task, seed, initial_sha)")
    if any(k in I for k in ("provenance", "rollout", "trial", "source")) or re.search(rb"witness|artifacts/|trial\.json", inst_b, re.I):
        # the agent reads this file in privileged mode: where the instance came from locates its solution (PROTOCOL §2.7)
        raise RuntimeError(f"{fz}: instance.json names its source rollout; provenance belongs in instances.json only")
    for key in ("summary", "scene", "standard_notes", "contact_rules"):
        hits = [m.group(0) for m in POSITION_IN_TEXT.finditer(D[key])]
        if hits:
            raise RuntimeError(f"descr/{code}.json {key}: a world coordinate {hits[:2]} in a text standard mode shows")
    ig = D.get("instance_goal")
    if ig and int(ig["seed"]) != int(I["seed"]):
        raise RuntimeError(f"descr/{code}.json instance_goal was written for seed {ig['seed']}, the instance has seed {I['seed']}")
    tool = (HERE / "shared/rcb_pandadyn.py").read_bytes()
    image = f"{REGISTRY}/eai-pandadyn:{version}"
    arms = int(D["arms"]); dim = 8 * arms
    module = module_of(code)
    acc, jerk = servo_fractions(module)
    horizon = float(I["horizon_s"])
    phases = D["phases"]
    def phases_block(std: bool) -> str:
        out = ""
        for n, p in enumerate(phases, 1):
            text = std_text(p["text"], f"{code} phase {p['name']}") if std else p["text"]
            out += f"{n}. **{p['name']}**: {text}\n"
        return out

    def fails_block(std: bool) -> str:
        if not D["task_failures"]:
            return "- the task's own failure conditions: none (only the rules below apply);\n"
        out = ""
        for f in D["task_failures"]:
            name, _, cond = f.partition(":")
            cond = std_text(cond, f"{code} failure {name}") if std else cond
            out += f"- {cond.strip().rstrip('.')} (`{name.strip()}`);\n"
        return out
    if arms == 1:
        intro = "one simulated **Franka Panda** arm (7 joints, its standard hand, and the task's tool where it has one)"
        layout = "`[joint1..7, aperture]`"
        arms_short = "one Franka Panda"
    else:
        intro = ("two simulated **Franka Panda** arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand "
                 "and the task's tool where it has one)")
        layout = "`[panda-0 joint1..7, panda-0 aperture, panda-1 joint1..7, panda-1 aperture]`"
        arms_short = "two Franka Pandas"
    params = ", ".join(f"`{k}` = {num(v)}" for k, v in I["parameters"].items())
    goals_fixed = D.get("world_goals_fixed") or ""
    goals_seeded = D.get("world_goals_seeded") or ""
    inst_goal = (ig or {}).get("text", "")
    goals_priv = ""
    if goals_fixed or goals_seeded or inst_goal:
        goals_priv = "\n**Goal geometry.** " + " ".join(x for x in (inst_goal, goals_fixed, goals_seeded) if x) + "\n"
    std_fixed = std_text(goals_fixed, f"{code} world_goals_fixed") if goals_fixed else ""
    goals_std = ("\n**Goal geometry.** " + " ".join(x for x in (inst_goal, std_fixed) if x) + "\n") if (std_fixed or inst_goal) else ""
    servo = f"65 % (speed), {round(100 * acc):d} % (acceleration) and {round(100 * jerk):d} % (jerk)"
    common = {"CODE": code, "TITLE": D["title"], "TASK": task, "INST": f"i{i:02d}", "PRIV": f"{base(task, i)}-privileged",
              "STD": f"{base(task, i)}-standard", "RT": f"{base(task, i)}-standard-realtime", "IMAGE": image, "CLIENT_IMAGE": CLIENT["CLIENT_IMAGE"].strip(),
              "ROBOT": "franka-panda" if arms == 1 else "franka-panda-bimanual", "FAMILY": f"{code.lower()}_{kebab(task.split('-', 1)[1]).replace('-', '_')}",
              "SEED": str(int(I["seed"])), "ARMS_SHORT": arms_short, "GOAL_TOML": toml_str("Task: " + D["summary"]),
              "KW_ARMS": '"single-arm"' if arms == 1 else '"bimanual"', "ROBOT_INTRO": intro, "N_PHASES": str(len(phases)), "HORIZON": num(horizon),
              "HORIZON_ROWS": str(int(round(horizon * 100))), "DIM": str(dim),
              "ACTION_LAYOUT": layout, "SERVO_LIMITS": servo, "ARM_FRAME": "Each arm's base pose is in the robot spec (`arms`).",
              "README_GOAL": D["summary"], "PHASE_NAMES": ", ".join(f"`{p['name']}`" for p in phases),
              "DIFFICULTY": D["difficulty_note"], "N_ORACLE": str(R["oracle_rows"]), "ORACLE_SIM_S": num(float(R["oracle_sim_time_s"])),
              "ORACLE_SHA": R["oracle_final_sha"][:16], "ENV_ID": I["env_id"], "INITIAL_SHA_SHORT": I["initial_sha"][:16],
              "FROZEN": f"{task}-i{i:02d}", "MAX_ROWS": f"{MAX_ROWS:,}", "MODULE_PATH": module.replace(".", "/") + ".py"}
    priv = {"SCENE_PRIVILEGED": D["scene_privileged"], "PARAMS": params, "GOALS": goals_priv, "SUMMARY": D["summary"],
            "ROBOT_SETUP": D["robot_setup"], "SCENE": D["scene"], "PHASES_BLOCK": phases_block(False), "FAILURES_BLOCK": fails_block(False),
            "CONTACT_RULES": D["contact_rules"]}
    std = {"GOALS_STD": goals_std, "STANDARD_NOTES": std_text(D["standard_notes"], f"{code} standard_notes"),
           "SUMMARY": std_text(D["summary"], f"{code} summary"), "ROBOT_SETUP": std_text(D["robot_setup"], f"{code} robot_setup"),
           "SCENE": std_text(D["scene"], f"{code} scene"), "PHASES_BLOCK": phases_block(True), "FAILURES_BLOCK": fails_block(True),
           "CONTACT_RULES": std_text(D["contact_rules"], f"{code} contact_rules")}
    texts = {"task_text": f"{D['title']}: {std['SUMMARY']} Phases, in order: " + "; ".join(f"{p['name']}: {std_text(p['text'], code)}" for p in phases)
                          + (f" Goal geometry: {goals_std.replace('**Goal geometry.** ', '').strip()}" if goals_std else ""),
             "episode": (f"one episode, no reset: it ends at the first control step where the task has succeeded (every phase in order) or "
                         f"failed (a failure event, a forbidden contact, a safety-limit violation, an object out of bounds, or the task's "
                         f"horizon of {num(horizon)} s of simulated time, {int(round(horizon * 100))} control steps), when your time is up, or "
                         f"on a simulator error; the simulated clock advances only with the control steps you run")}
    out: dict[str, dict[str, tuple[bytes, int]]] = {}
    modes = [("privileged", priv), ("standard", std)]
    if code in REALTIME:
        rtf, S = REALTIME[code]
        modes.append(("standard-realtime", {**std, "SLOWDOWN": str(S), "RTF": rtf, "WALL_MS": str(10 * S),
                                            "HORIZON_WALL_S": num(round(horizon * S, 1)), "RT_RESETS": str(RT_RESETS),
                                            "RT_RESETS_PLUS1": str(RT_RESETS + 1)}))
    for mode, extra in modes:
        common["AGENT_TIMEOUT_S"] = str(agent_timeout(mode))
        files: dict[str, tuple[bytes, int]] = {}
        tdir = HERE / "template" / ("realtime" if mode == "standard-realtime" else mode)
        for p in sorted(tdir.rglob("*")):
            if not p.is_file() or "__pycache__" in p.parts:
                continue
            rel = p.relative_to(tdir).as_posix()
            if rel.endswith(".tmpl"):
                rel = rel[:-5]; data = fill(p.read_text(), {**common, **extra}).encode()
            else:
                data = p.read_bytes()
            files[rel] = (data, 0o755 if rel.endswith(".sh") else 0o644)
        if mode == "privileged":
            for rel in ("environment/rcb_pandadyn.py", "tests/rcb_pandadyn.py"):
                files[rel] = (tool, 0o644)
            for rel in ("environment/instance.json", "tests/instance.json"):
                files[rel] = (inst_b, 0o644)
            files["solution/oracle_actions.npy"] = (oracle_b, 0o644)
        elif mode == "standard-realtime":
            files["environment/sim/rcb_pandadyn.py"] = (tool, 0o644)
            files["environment/sim/instance.json"] = (inst_b, 0o644)
            files["environment/sim/texts.json"] = ((json.dumps(texts, indent=1, ensure_ascii=False) + "\n").encode(), 0o644)
            for rel, src in (("environment/rcb_client.py", RT_LAYER / "realtime/rcb_client.py"), ("environment/rcb1.py", LAYER / "rcb1.py"),
                             ("environment/sim/rcb_realtime.py", RT_LAYER / "realtime/rcb_realtime.py"),
                             ("environment/sim/rcb_service.py", RT_LAYER / "standard/rcb_service.py"),
                             ("environment/sim/rcb1.py", LAYER / "rcb1.py"), ("tests/grade.py", RT_LAYER / "standard/grade.py")):
                files[rel] = (src.read_bytes(), 0o644)
            req = CLIENT.get("CLIENT_REQUIREMENTS", "client-requirements.txt").strip()
            files["environment/client-requirements.txt"] = ((LAYER / req).read_bytes(), 0o644)
            files["solution/oracle_qpos.npy"] = (oracle_b, 0o644)          # one row per control step, planned with `hold`
        else:
            files["environment/sim/rcb_pandadyn.py"] = (tool, 0o644)
            files["environment/sim/instance.json"] = (inst_b, 0o644)
            files["environment/sim/texts.json"] = ((json.dumps(texts, indent=1, ensure_ascii=False) + "\n").encode(), 0o644)
            for rel, src in (("environment/rcb_client.py", "rcb_client.py"), ("environment/rcb1.py", "rcb1.py"),
                             ("environment/sim/rcb_limited.py", "rcb_limited.py"), ("environment/sim/rcb1.py", "rcb1.py"),
                             ("environment/sim/run.sh", "run.sh")):
                files[rel] = ((LAYER / src).read_bytes(), 0o755 if rel.endswith(".sh") else 0o644)
            req = CLIENT.get("CLIENT_REQUIREMENTS", "client-requirements.txt").strip()
            files["environment/client-requirements.txt"] = ((LAYER / req).read_bytes(), 0o644)
            files["solution/oracle_qpos.npy"] = (oracle_b, 0o644)          # one row per control step, streamed with `hold`
            files["solution/oracle_meta.json"] = (json.dumps({"K": 1, "interpolate": "hold", "source": "the privileged oracle's rows"}, indent=1).encode() + b"\n", 0o644)
        out[f"{base(task, i)}-{mode}"] = files
    return out


def normalized(planned: dict[str, dict[str, tuple[bytes, int]]], normalize) -> dict[str, dict[str, tuple[bytes, int]]]:
    out = {}
    with tempfile.TemporaryDirectory(prefix="pandadyn_mk_") as td:
        for name, files in planned.items():
            for rel, (data, mode) in files.items():
                p = pathlib.Path(td) / name / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
                os.chmod(p, 0o755 if mode & 0o100 else 0o644)
        for name in planned:
            normalize(pathlib.Path(td) / name)
        for name in planned:
            t = pathlib.Path(td) / name
            out[name] = {p.relative_to(t).as_posix(): (p.read_bytes(), 0o755 if p.stat().st_mode & 0o100 else 0o644)
                         for p in sorted(t.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}
    return out


def sync(task: pathlib.Path, files: dict, check: bool) -> list[str]:
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
                m = p.stat().st_mode & 0o777
                os.chmod(p, m | 0o111 if mode & 0o100 else m & ~0o111)
    if not check and task.exists():
        for d in sorted((p for p in task.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
            if not any(d.iterdir()):
                d.rmdir()
    return diffs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--only", default="", help="comma-separated task codes (S02,D04); default: every frozen instance")
    a = ap.parse_args()
    reg = json.loads((HERE / "instances.json").read_text())["tasks"]
    version = (ROOT / "images/pandadyn/VERSION").read_text().strip()
    normalize = normalizer()
    diffs, made = [], set()
    for task in sorted(reg):
        if a.only and task.split("-", 1)[0] not in a.only.split(","):
            continue
        for name, files in normalized(plan_instance(task, reg[task], version), normalize).items():
            made.add(name); diffs += sync(ROOT / "tasks" / name, files, a.check)
    if not a.only:
        for t in sorted((ROOT / "tasks").glob("pandadyn-*")):
            if t.is_dir() and t.name not in made:
                diffs.append(f"stale  {t.name} (not in instances.json)")
    for d in diffs:
        print(d)
    print(f"{'checked' if a.check else 'generated'} {len(made)} Panda Dynamic Scenes task dirs: {len(diffs)} difference(s)")
    return 1 if (a.check and diffs) else 0


if __name__ == "__main__":
    sys.exit(main())
