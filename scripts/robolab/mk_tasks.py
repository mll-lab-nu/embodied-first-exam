#!/usr/bin/env python3
"""Generate the RoboLab tasks: tasks/robolab-<family>-i00-privileged and tasks/robolab-<family>-i00-standard (standard
mode, eai-standard/2.2) for every family of scripts/robolab/families.json with "tasks": true (docs/benchmarks/robolab.md).

    python3 scripts/robolab/mk_tasks.py                    # (re)write every RoboLab task dir; `git diff tasks/` stays empty
    python3 scripts/robolab/mk_tasks.py --check            # write nothing; exit 1 if a task dir differs from the generator's
    python3 scripts/robolab/mk_tasks.py banana_in_bowl ... # these families only
Then `cd tasks && harbor add --scan .` when a digest changed. Needs only Python 3 (no simulator).

Inputs, all in the repository:
  scripts/robolab/families.json          per family: RoboLab's task class and file, the goal, the success term's source and
                                         its notes, the texts of both modes, the oracle level and the cited positives
                                         (`tasks: false`: frozen, not generated yet)
  scripts/robolab/instances/<f>.json     the frozen instance (RoboLab's canonical seeded reset), written in the image by
                                         `python rcb_robolab.py make-instance --task <f> --seed 0 --out <f>.json`
  scripts/robolab/oracles/<f>/           families with a reference solution: oracle_<f>.py (privileged) and the standard
                                         oracle's joint targets oracle_qpos.npy + oracle_meta.json, recorded from its run
  scripts/robolab/shared/                rcb_robolab.py (the tooling: privileged environment/ + tests/, standard
                                         environment/sim/; one TASKS registry for every family) and ref_primitives.py
                                         (the reference solutions' task-level skills: solution/ of oracle families only)
  scripts/robolab/template/<mode>/       every other task file; a *.tmpl file is filled with the family's values (@@KEY@@)
  scripts/eai_standard/                  the eai-standard/2.2 layer, copied unchanged (rcb_client.py, rcb1.py; sim/
                                         rcb_limited.py, rcb1.py, run.sh) and the standard client: client.env (the base
                                         image) + client-requirements.txt (the pip pins, copied into environment/)
  images/robolab/VERSION                 the base image tag
Both twins of a family are written to a scratch directory, passed through scripts/task_conventions.py's normalize()
(PROTOCOL v1.0 conventions: names, README layout, no results/) and then synced into tasks/: a task dir holds exactly what
the generator writes, other files are removed. Results are not kept in task dirs (PROTOCOL D3): the cited positives are
named by trial id with their results-site and Hugging Face links."""
from __future__ import annotations
import argparse, json, os, pathlib, re, shutil, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = ROOT / "scripts/robolab"
LAYER = ROOT / "scripts/eai_standard"
REGISTRY = "ghcr.io/mll-lab-nu"
CLIENT = dict(l.split("=", 1) for l in (LAYER / "client.env").read_text().splitlines() if "=" in l and not l.startswith("#"))
RUN_ID = "codex-gpt6_luna-xhigh"            # the run whose trials are the cited positives (results site, Hugging Face)
REVIEW_PR = "#3"                           # the pull request with the per-family review (PROTOCOL §2.7): dev/qineng = PR #3
# The agent's egress is the model APIs only (owner decision 2026-10-10, board 0072; docs/benchmarks/robolab.md, Network): the
# templates' `[agent]` blocks hold the two lines `scripts/set_agent_egress.py allowlist` writes, with that script's HOSTS (one
# list for every task, ci_checks/check-verifier-isolation.sh).
_HOSTS = re.search(r"(?ms)^HOSTS = \[(.*?)\]", (ROOT / "scripts/set_agent_egress.py").read_text())
ALLOWED_HOSTS = ", ".join(f'"{h}"' for h in re.findall(r'"([^"]+)"', _HOSTS.group(1) if _HOSTS else ""))
if not ALLOWED_HOSTS:
    raise RuntimeError("scripts/set_agent_egress.py has no HOSTS")


def toml_str(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def slug(fam: str) -> str:
    """The family's base name; the task dirs are <base>-privileged and <base>-standard (PROTOCOL §2.2)."""
    return f"robolab-{fam.replace('_', '-')}-i00"


def task_dir(fam: str, mode: str) -> str:
    return f"{slug(fam)}-{mode}"


def normalizer():
    """scripts/task_conventions.py's normalize(task_dir): every generator ends with it (PROTOCOL v1.0)."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from task_conventions import normalize
    return normalize


def fill(text: str, values: dict) -> str:
    for k, v in values.items():
        text = text.replace(f"@@{k}@@", v)
    if "@@" in text:
        raise RuntimeError(f"unfilled placeholder near {text[text.index('@@'):][:40]!r}")
    return text


def where(p: dict) -> str:
    """Where a cited positive is published: its trial log on the results site (which links the replay), or why not."""
    return p["site_log"] or "not published: its rcb-limited/2.0 batch was withdrawn for the agent's stale wrist-camera pose; grader unaffected"


def positives_text(fam: str, F: dict) -> str:
    return "; ".join(f"{p['trial']} ({task_dir(fam, p['mode'])}, run {RUN_ID}, {p['batch']}, {p['host']}; {where(p)})" for p in F["positives"])


def positives_list(fam: str, F: dict) -> str:
    out = []
    for p in F["positives"]:
        links = (f"[trial log]({p['site_log']})" + (f", [replay video]({p['hf_replay']})" if p["hf_replay"] else "")) if p["site_log"] else where(p)
        out.append(f"- `{p['trial']}` ({p['mode']} mode, run `{RUN_ID}`, batch `{p['batch']}`, host {p['host']}): {links}")
    return "\n".join(out)


def oracle_level(F: dict, mode: str) -> str:
    """families.json `oracle`: one level for both modes, or {"privileged": ..., "standard": ...} (each task.toml has its own)."""
    return F["oracle"] if isinstance(F["oracle"], str) else F["oracle"][mode]


def oracle_evidence(fam: str, F: dict, mode: str) -> str | None:
    """task.toml `oracle_evidence`: the positives for "none"; families.json's own text otherwise (required for "partial";
    for "full" it cites the recorded oracle runs the level rests on)."""
    if oracle_level(F, mode) == "none":
        return (f"No reference solution: RoboLab ships no expert or planner. Positive examples graded 1 by the separate verifier: "
                f"{positives_text(fam, F)}. Human review per family (PROTOCOL §2.7).")
    return (F.get("oracle_evidence") or {}).get(mode)


def reference_none(fam: str, F: dict) -> str:
    return (f"None: RoboLab ships no expert or planner, and no reference solution has been written for this family "
            f"(`oracle = \"none\"`). Positive examples, model trials the separate verifier scored 1:\n{positives_list(fam, F)}")


def review_note(F: dict, mode: str) -> str:
    lvl = oracle_level(F, mode)
    if lvl == "full":
        return ""
    where = f"PR {REVIEW_PR}" if REVIEW_PR else "the pull request that adds this task"
    head = "No oracle" if lvl == "none" else f"Oracle `{lvl}` (see Reference solution)"
    return (f"\n{head}; human review in {where} (PROTOCOL §2.7: per family, this task and its twin, a positive example "
            f"and the `nop` result).\n")


def objects_block(F: dict) -> str:
    objs = ", ".join(f"`{o}`" for o in F["objects"] + ["table"])
    cond = ", ".join(f"`{c}`" for c in F["conditionals"])
    note = F["note"].strip()
    return (f"The scene objects are the env's rigid objects (`s.objects()`: {objs}; see\n"
            f"`/opt/robolab/robolab/tasks/{F['task_file']}`). RoboLab's success predicate is the `success` termination\n"
            f"term in that file ({cond} in `/opt/robolab/robolab/core/task/conditionals.py`); it also ends the episode:\n"
            f"```python\n{F['terms']}\n```\n" + (f"{note}\n" if note else ""))


def plan_family(fam: str, F: dict, version: str) -> dict[str, dict[str, tuple[bytes, int]]]:
    """{task dir name: {relative path: (content, mode)}} for both modes of one family."""
    inst = (HERE / "instances" / f"{fam}.json").read_bytes()
    I = json.loads(inst)
    if I.get("task") != fam or int(I.get("seed", -1)) != F["seed"] or I.get("text") != F["goal"]:
        raise RuntimeError(f"{fam}: instances/{fam}.json does not match families.json (task, seed, text)")
    if "none" in (oracle_level(F, "privileged"), oracle_level(F, "standard")) and not F["positives"]:
        raise RuntimeError(f"{fam}: oracle none and no positive example: not a task yet (PROTOCOL §2.7)")
    for mode in ("privileged", "standard"):
        if oracle_level(F, mode) == "partial" and not oracle_evidence(fam, F, mode):
            raise RuntimeError(f"{fam}: oracle partial ({mode}) needs its oracle_evidence in families.json")
    tool = (HERE / "shared/rcb_robolab.py").read_bytes()
    image = f"{REGISTRY}/eai-robolab:{version}"
    def per_mode(mode: str) -> dict:
        ev = oracle_evidence(fam, F, mode)
        return {"ORACLE": oracle_level(F, mode), "REVIEW_NOTE": review_note(F, mode),
                "ORACLE_EVIDENCE_LINE": f'oracle_evidence = "{toml_str(ev)}"\n' if ev else ""}

    def reference(mode: str, text: str) -> str:
        """The README's Reference solution: the oracle (its level and evidence are in the key table's Oracle row), or the
        cited positives when there is none."""
        return reference_none(fam, F) if oracle_level(F, mode) == "none" else text

    common = {"FAMILY": fam, "SLUG": slug(fam), "PRIV": task_dir(fam, "privileged"), "STD": task_dir(fam, "standard"),
              "SEED": str(F["seed"]), "IMAGE": image, "IMAGE_VERSION": version, "ALLOWED_HOSTS": ALLOWED_HOSTS,
              "CLIENT_IMAGE": CLIENT["CLIENT_IMAGE"].strip()}
    priv = {"GOAL": F["goal"], "GOAL_TOML": toml_str(F["goal"]), "ROBOLAB_TASK": F["robolab_task"], "README_GOAL": F.get("readme_goal", F["goal"]),
            "DIFFICULTY": F["difficulty"], "OBJECTS_BLOCK": objects_block(F), **per_mode("privileged"),
            "REFERENCE_SOLUTION": reference("privileged", F.get("reference_solution", ""))}
    std = {"INSTANCE_TEXT": toml_str(I["text"]), "STANDARD_GOAL": F["standard_goal"], "STANDARD_OBJECTS": F["standard_objects"].rstrip() + "\n",
           **per_mode("standard"),
           "REFERENCE_SOLUTION": reference("standard", "`solution/oracle_replay.py` streams the privileged oracle's joint targets "
                                           "(`oracle_qpos.npy`, one row per control step, `hold`) as one-second `joint_position` chunks "
                                           "through the client; after a service crash it waits for the resumed episode and continues from "
                                           "the control step the service reports.")}
    out: dict[str, dict[str, tuple[bytes, int]]] = {}
    for mode, extra in (("privileged", priv), ("standard", std)):
        name = task_dir(fam, mode)
        files: dict[str, tuple[bytes, int]] = {}
        has_solution = oracle_level(F, mode) != "none"
        tdir = HERE / "template" / mode
        for p in sorted(tdir.rglob("*")):
            if not p.is_file() or "__pycache__" in p.parts:
                continue
            rel = p.relative_to(tdir).as_posix()
            if rel.startswith("solution/") and not has_solution:
                continue                     # oracle "none": no solution/ at all (PROTOCOL §2.7, D2)
            if rel.endswith(".tmpl"):
                rel = rel[:-5]; data = fill(p.read_text(), {**common, **extra}).encode()
            else:
                data = p.read_bytes()
            files[rel] = (data, 0o755 if rel.endswith(".sh") else 0o644)
        if mode == "privileged":
            for rel in ("environment/rcb_robolab.py", "tests/rcb_robolab.py"):
                files[rel] = (tool, 0o644)
            for rel in ("environment/instance.json", "tests/instance.json"):
                files[rel] = (inst, 0o644)
            if has_solution:
                files[f"solution/oracle_{fam}.py"] = ((HERE / "oracles" / fam / f"oracle_{fam}.py").read_bytes(), 0o644)
                files["solution/ref_primitives.py"] = ((HERE / "shared/ref_primitives.py").read_bytes(), 0o644)
        else:
            files["environment/sim/rcb_robolab.py"] = (tool, 0o644)
            files["environment/sim/instance.json"] = (inst, 0o644)
            for rel, src in (("environment/rcb_client.py", "rcb_client.py"), ("environment/rcb1.py", "rcb1.py"),
                             ("environment/sim/rcb_limited.py", "rcb_limited.py"), ("environment/sim/rcb1.py", "rcb1.py"),
                             ("environment/sim/run.sh", "run.sh")):
                files[rel] = ((LAYER / src).read_bytes(), 0o755 if rel.endswith(".sh") else 0o644)
            req = CLIENT.get("CLIENT_REQUIREMENTS", "client-requirements.txt").strip()
            files["environment/client-requirements.txt"] = ((LAYER / req).read_bytes(), 0o644)   # the shared pins, byte-identical
            if has_solution:
                for f in ("oracle_qpos.npy", "oracle_meta.json"):
                    files[f"solution/{f}"] = ((HERE / "oracles" / fam / f).read_bytes(), 0o644)
        out[name] = files
    return out


def normalized(planned: dict[str, dict[str, tuple[bytes, int]]], normalize) -> dict[str, dict[str, tuple[bytes, int]]]:
    """Write a family's twins to a scratch tasks/ dir, run task_conventions.normalize() on each (it reads the twin for the
    README's key table) and read them back: what the generator commits is the normalized task."""
    out = {}
    with tempfile.TemporaryDirectory(prefix="robolab_mk_") as td:
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
                m = p.stat().st_mode & 0o777          # git keeps only the executable bit: set or clear it, keep the rest
                os.chmod(p, m | 0o111 if mode & 0o100 else m & ~0o111)
    if not check and task.exists():                  # directories left empty by a removal
        for d in sorted((p for p in task.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
            if not any(d.iterdir()):
                d.rmdir()
    return diffs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("families", nargs="*"); ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    fams = json.loads((HERE / "families.json").read_text())["families"]
    version = (ROOT / "images/robolab/VERSION").read_text().strip()
    todo = a.families or [f for f, F in fams.items() if F["tasks"]]
    unknown = [f for f in todo if f not in fams or not fams[f]["tasks"]]
    if unknown:
        raise SystemExit(f"not generated (unknown, or tasks: false in families.json): {unknown}")
    normalize = normalizer()
    diffs = []
    for fam in todo:
        for name, files in normalized(plan_family(fam, fams[fam], version), normalize).items():
            diffs += sync(ROOT / "tasks" / name, files, a.check)
    if not a.families:                                # task dirs of families that are no longer generated
        made = {task_dir(f, m) for f, F in fams.items() if F["tasks"] for m in ("privileged", "standard")}
        for t in sorted((ROOT / "tasks").glob("robolab-*")):
            if t.is_dir() and t.name not in made:
                diffs.append(f"stale  {t.name} (not in families.json: remove it, or set tasks: true)")
    for d in diffs:
        print(d)
    n = len(todo) * 2
    print(f"{'checked' if a.check else 'generated'} {n} RoboLab task dirs ({len(todo)} families): {len(diffs)} difference(s)")
    return 1 if (a.check and diffs) else 0


if __name__ == "__main__":
    sys.exit(main())
