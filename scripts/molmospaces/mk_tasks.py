#!/usr/bin/env python3
"""Generate the MolmoSpaces tasks: tasks/molmospaces-<family>-i00-privileged and -standard (eai-standard/2.2) for every
frozen instance in scripts/molmospaces/instances/ (docs/benchmarks/molmospaces.md).

    python3 scripts/molmospaces/mk_tasks.py              # (re)write every MolmoSpaces task dir; `git diff tasks/` stays empty
    python3 scripts/molmospaces/mk_tasks.py --check      # write nothing; exit 1 if a task dir differs from the generator's
Then `cd tasks && harbor add --scan .` when a digest changed. Needs only Python 3 (no simulator).

Inputs, all in the repository:
  scripts/molmospaces/families.json         per family: the upstream package, robot, control rate, variants, the kept
                                            episode, the success rule in words and the difficulty; per robot: its
                                            description, short name and units
  scripts/molmospaces/instances/<f>-i00.json the frozen upstream episode + the numbers the texts quote (make_instances.py)
  scripts/molmospaces/shared/rcb_molmospaces.py   the tooling: privileged environment/ + tests/, standard environment/sim/
  scripts/molmospaces/template/<mode>/      every other task file; a *.tmpl file is filled with the instance's values (@@KEY@@)
  scripts/eai_standard/                     the eai-standard/2.2 layer, copied unchanged, and the standard client pins
  images/molmospaces/VERSION                the base image tag
Both twins are written to a scratch directory, passed through scripts/task_conventions.py's normalize() and synced into
tasks/: a task dir holds exactly what the generator writes."""

import argparse, json, os, pathlib, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = ROOT / "scripts/molmospaces"
LAYER = ROOT / "scripts/eai_standard"
REGISTRY = "ghcr.io/mll-lab-nu"
CLIENT = dict(
    l.split("=", 1) for l in (LAYER / "client.env").read_text().splitlines() if "=" in l and not l.startswith("#")
)
RUN = "codex-gpt6_1_sol-high"  # GPT-6.1 Sol, Codex, effort high, 2026-10-16: not yet on the results site
# Per family, that run's privileged trial on the kept episode that the separate verifier graded 1, and its batch.
POSITIVE = {
    "pick": "molmospaces-pick-i00-privileged__Y6SSCTZ",
    "pick-and-place": "molmospaces-pick-and-place-i00-p__w3GRFg3",
    "pick-and-place-next-to": "molmospaces-pick-and-place-next__HMjmn5X",
    "pick-and-place-color": "molmospaces-pick-and-place-color__gde8im8",
    "open": "molmospaces-open-i00-privileged__bVqNR4u",
    "close": "molmospaces-close-i00-privileged__8SX5TrW",
    "navigate-to": "molmospaces-navigate-to-i00-priv__YWMd22o",
    "open-door": "molmospaces-open-door-i00-privil__EJchtFe",
}
BATCH = {"open": "molmo-harder-sol", "navigate-to": "molmo-v2-sol-rby1", "open-door": "molmo-v2-sol-rby1"}  # else molmo-v2-sol
# The verifier's replays ran out of time on a loaded host (replay_timed_out, infra_error: before the 2026-10-16 limit):
# graded again offline, two fresh replays of the trial's trajectory in the task's image without a time limit.
REGRADED = {"pick-and-place", "pick-and-place-next-to", "pick-and-place-color"}
IMAGE_OF = {"open": "0.2.4"}  # a trial on an earlier build of the image (not published; same instance, same assets)
REVIEW_PR = 276  # the pull request whose human review covers these tasks (PROTOCOL §2.7)


def oracle_evidence(family: str) -> str:
    regraded = (
        "; its verifier's replays ran out of time on a loaded host (the earlier 500 s limit), so it was graded 1 "
        "offline with the verifier's replay tool: two fresh replays in the task's image, no time limit, both successes "
        "with equal final hashes"
        if family in REGRADED
        else ""
    )
    image = f", image {IMAGE_OF[family]}, the same instance" if family in IMAGE_OF else ""
    return (
        f"no reference solution (MolmoSpaces' planners and grasp files are not shipped); positive example graded 1"
        f"{'' if family in REGRADED else ' by the separate verifier'}: {POSITIVE[family]} (run {RUN}, batch "
        f"{BATCH.get(family, 'molmo-v2-sol')}, 2026-10-16{image}{regraded}); human review in PR #{REVIEW_PR}"
    )


LAYER_FILES = (
    ("environment/rcb_client.py", "rcb_client.py"),
    ("environment/rcb1.py", "rcb1.py"),
    ("environment/sim/rcb_limited.py", "rcb_limited.py"),
    ("environment/sim/rcb1.py", "rcb1.py"),
    ("environment/sim/run.sh", "run.sh"),
)


def task_dir(inst: dict, mode: str) -> str:
    return f"molmospaces-{inst['family']}-{inst['instance']}-{mode}"


def toml_str(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def fill(text: str, values: dict) -> str:
    for k, v in values.items():
        text = text.replace(f"@@{k}@@", str(v))
    if "@@" in text:
        raise RuntimeError(f"unfilled placeholder near {text[text.index('@@') :][:40]!r}")
    return text


def gripper_t0(inst: dict) -> str:
    """The Franka gripper at t = 0: open, and its controller target is the episode's (0, or 255 in some episodes)."""
    t0 = inst["t0"]
    if "gripper" not in t0["layout"]:
        return ""
    target = t0["targets"][t0["layout"].index("gripper")]
    if target == 0:
        return " At t = 0 the gripper is open and its target is 0."
    return (
        f" At t = 0 the gripper is open, but its controller target is already {target:g} (closed): holding the "
        "current targets closes it; command 0 to keep it open."
    )


def dt_max(period_ms: float) -> str:
    """The largest whole multiple of the control period within 0.5 s, when it is not 0.5 s itself."""
    top = int(500 // period_ms) * period_ms / 1000
    return "" if abs(top - 0.5) < 1e-9 else f": up to {top:g} s"


def values(inst: dict, fam: dict, robot: dict, version: str) -> dict:
    f, ep = inst["facts"], inst["episode"]
    goal = f["goal"].strip().rstrip(".") + "."
    goal = goal[0].upper() + goal[1:]
    layout = inst["t0"]["layout"]
    nav = inst["family"] == "navigate-to"
    return {
        "FAMILY": inst["family"],
        "PRIV": task_dir(inst, "privileged"),
        "STD": task_dir(inst, "standard"),
        "GOAL": goal,
        "GOAL_TOML": toml_str(goal),
        "VARIANT": inst["variant"],
        "SUCCESS": fam["success"].format(**f),
        "DIFFICULTY": fam["difficulty"],
        "ROBOT_TEXT": robot["text"],
        "ROBOT_SHORT": robot["short"],
        "ROBOT_TAX": robot["taxonomy"],
        "UNITS": robot["units"],
        "UPSTREAM": inst["upstream"]["name"],
        "BENCHMARK": inst["upstream"]["benchmark"],
        "PACKAGE": inst["upstream"]["package"],
        "EPISODE_INDEX": inst["upstream"]["episode_index"],
        "HOUSE": f"{ep['scene_dataset']} {ep['data_split']} {ep['house_index']}",
        "HORIZON_STEPS": f["horizon_steps"],
        "HORIZON_S": f["horizon_s"],
        "CONTROL_HZ": f"{f['control_hz']:g}",
        "DT": f"{inst['policy_dt_ms'] / 1000:g}",
        "DT_MAX": dt_max(inst["policy_dt_ms"]),
        "GRIPPER_T0": gripper_t0(inst),
        "DIM": inst["t0"]["action_dim"],
        "LAYOUT": ", ".join(f"`{c}`" for c in layout),
        "TCP": inst["t0"]["tcp_frames"][0],
        "CAMERAS": ", ".join(f"`{c}`" for c in inst["agent_cameras"]),
        "NAV_NOTE": " and its text replaced by upstream NavToObjTask's own description (the package's is wrong)"
        if nav
        else "",
        "IMAGE": f"{REGISTRY}/eai-molmospaces:{version}",
        "CLIENT_IMAGE": CLIENT["CLIENT_IMAGE"].strip(),
        "ORACLE_EVIDENCE": toml_str(oracle_evidence(inst["family"])),
        "REVIEW_PR": REVIEW_PR,
        "UNITS_YAML": json.dumps(robot["units"]).replace("$", "$$"),
    }


def plan(inst_path: pathlib.Path, fams: dict, version: str) -> dict[str, dict[str, tuple[bytes, int]]]:
    """{task dir name: {relative path: (content, mode)}} for both modes of one instance."""
    raw = inst_path.read_bytes()
    inst = json.loads(raw)
    fam, robot = fams["families"][inst["family"]], fams["robots"][inst["robot_config"]]
    if (
        inst_path.stem != f"{inst['family']}-{inst['instance']}"
        or inst["upstream"]["package"] != fam["package"]
        or inst["instance"] != "i00"
        or inst["upstream"]["episode_index"] != fam["keep"]
    ):
        raise RuntimeError(f"{inst_path.name} does not match families.json (family, package, the kept episode as i00)")
    vals = values(inst, fam, robot, version)
    tool = (HERE / "shared/rcb_molmospaces.py").read_bytes()
    out = {}
    for mode in ("privileged", "standard"):
        files: dict[str, tuple[bytes, int]] = {}
        tdir = HERE / "template" / mode
        for p in sorted(tdir.rglob("*")):
            if not p.is_file() or "__pycache__" in p.parts:
                continue
            rel = p.relative_to(tdir).as_posix()
            if rel.endswith(".tmpl"):
                rel = rel[:-5]
                data = fill(p.read_text(), vals).encode()
            else:
                data = p.read_bytes()
            files[rel] = (data, 0o755 if rel.endswith(".sh") else 0o644)
        if mode == "privileged":
            for rel in ("environment/rcb_molmospaces.py", "tests/rcb_molmospaces.py"):
                files[rel] = (tool, 0o644)
            for rel in ("environment/instance.json", "tests/instance.json"):
                files[rel] = (raw, 0o644)
        else:
            files["environment/sim/rcb_molmospaces.py"] = (tool, 0o644)
            files["environment/sim/instance.json"] = (raw, 0o644)
            for rel, src in LAYER_FILES:
                files[rel] = ((LAYER / src).read_bytes(), 0o755 if rel.endswith(".sh") else 0o644)
            req = CLIENT["CLIENT_REQUIREMENTS"].strip()
            files["environment/client-requirements.txt"] = ((LAYER / req).read_bytes(), 0o644)
        out[task_dir(inst, mode)] = files
    return out


def normalized(planned: dict, normalize) -> dict:
    """Write the twins to a scratch tasks/ dir, run task_conventions.normalize() on each and read them back."""
    out = {}
    with tempfile.TemporaryDirectory(prefix="molmospaces_mk_") as td:
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
    have = (
        {p.relative_to(task).as_posix() for p in task.rglob("*") if p.is_file() or p.is_symlink()}
        if task.exists()
        else set()
    )
    have = {h for h in have if "__pycache__" not in h.split("/")}
    for rel in sorted(have - set(files)):
        diffs.append(f"remove {task.name}/{rel}")
        if not check:
            (task / rel).unlink()
    for rel, (data, mode) in sorted(files.items()):
        p = task / rel
        same = (
            p.is_file()
            and not p.is_symlink()
            and p.read_bytes() == data
            and bool(p.stat().st_mode & 0o100) == bool(mode & 0o100)
        )
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
    a = ap.parse_args()
    fams = json.loads((HERE / "families.json").read_text())
    version = (ROOT / "images/molmospaces/VERSION").read_text().strip()
    sys.path.insert(0, str(ROOT / "scripts"))
    from task_conventions import normalize

    instances = sorted((HERE / "instances").glob("*.json"))
    diffs, made = [], set()
    for p in instances:
        for name, files in normalized(plan(p, fams, version), normalize).items():
            made.add(name)
            diffs += sync(ROOT / "tasks" / name, files, a.check)
    for t in sorted((ROOT / "tasks").glob("molmospaces-*")):
        if t.is_dir() and t.name not in made:
            diffs.append(f"stale  {t.name} (no instance for it: remove it)")
    for d in diffs:
        print(d)
    print(
        f"{'checked' if a.check else 'generated'} {len(made)} MolmoSpaces task dirs ({len(instances)} instances): {len(diffs)} difference(s)"
    )
    return 1 if (a.check and diffs) else 0


if __name__ == "__main__":
    sys.exit(main())
