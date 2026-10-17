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
# The agent's egress is the model APIs and the package registries (owner decisions 2026-10-10 / 10-11, board 0072; docs/benchmarks/robolab.md, Network): the
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


# The agent's time cutoff per mode (PROTOCOL §2.12): this benchmark's own number, written into every task's `[agent]
# timeout_sec`, the one source; normalize renders from it the instruction's closing `## Time limit`, the README row and
# the sim service's wall clock. To change it (an owner decision; the pull request states old -> new), edit it here and
# regenerate.
CUTOFF_SEC = 3600   # the same in both modes (PROTOCOL §2.15)


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
    return "; ".join(f"{p['trial']} ({task_dir(fam, p['mode'])} before 2026-10-14, run {RUN_ID}, {p['batch']}, "
                     f"{p['host']}; {where(p)})" for p in F["positives"])


def positives_list(fam: str, F: dict) -> str:
    out = []
    for p in F["positives"]:
        links = (f"[trial log]({p['site_log']})" + (f", [replay video]({p['hf_replay']})" if p["hf_replay"] else "")) if p["site_log"] else where(p)
        out.append(f"- `{p['trial']}` ({p['mode']} mode, on this task before 2026-10-14; run `{RUN_ID}`, batch `{p['batch']}`, "
                   f"host {p['host']}): {links}")
    return "\n".join(out)


def oracle_level(F: dict, mode: str) -> str:
    """families.json `oracle`: one level for both modes, or {"privileged": ..., "standard": ...} (each task.toml has its own)."""
    return F["oracle"] if isinstance(F["oracle"], str) else F["oracle"][mode]


I01_DEFAULT = ("The positives were graded before 2026-10-14 (one-finger gripper contact, no settle hold); not re-graded "
               "under the 2026-10-14 term unless stated here.")


def oracle_evidence(fam: str, F: dict, mode: str) -> str | None:
    """task.toml `oracle_evidence`: the positives for "none"; families.json's own text otherwise (required for "partial";
    for "full" it cites the recorded oracle runs the level rests on). For "none", what the 2026-10-14 re-grades found
    (families.json `i01_evidence`: one text, or {"privileged": ..., "standard": ...})."""
    if oracle_level(F, mode) == "none":
        i01 = F.get("i01_evidence") or I01_DEFAULT
        i01 = i01 if isinstance(i01, str) else i01.get(mode) or I01_DEFAULT
        return (f"No reference solution: RoboLab ships no expert or planner. Positive examples graded 1 by the separate verifier: "
                f"{positives_text(fam, F)}. {i01} Human review per family (PROTOCOL §2.7).")
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


# The texts below state rules the grader applies, read from the grader's own sources so that they cannot drift from it
# (2026-10-16 instruction audit): the on-table families of the tooling, and the standard collect hook and verifier.
_TOOL_SRC = (HERE / "shared/rcb_robolab.py").read_text()
_ON_TABLE = re.search(r"(?m)^ON_TABLE = \(([^)]*)\)", _TOOL_SRC)
ON_TABLE = tuple(re.findall(r'"([^"]+)"', _ON_TABLE.group(1))) if _ON_TABLE else ()
if not ON_TABLE or 'term.params = {**params, "surface": "table"}' not in _TOOL_SRC:
    raise RuntimeError("shared/rcb_robolab.py: ON_TABLE or its term replacement not found")
# RoboLab v0.3.1: WorldState.is_supported_on_surface(obj, surface) defaults, the support test of the on-table term
SUPPORT_RULE = (": the contact force between the object and the table is at least 0.1 N and points upwards, within 45° "
                "of vertical. An object held in the air, resting only on other objects, or dropped on the floor does not count")
SUPPORT_TEXT = "rest on the table top" + SUPPORT_RULE
SUPPORT_SRC = "RoboLab's `WorldState.is_supported_on_surface`, `/opt/robolab/robolab/core/world/world_state.py`"


def on_table_terms(F: dict) -> str:
    """The success term as graded here for an ON_TABLE family: the tooling's replacement of upstream's term."""
    t, n = re.subn(r"func=object_outside_of,", "func=object_outside_of_and_on_surface,", F["terms"])
    t, m = re.subn(r"params=\{([^{}]*?)\s*\}", lambda g: "params={" + g.group(1) + ', "surface": "table"}', t)
    if n != 1 or m != 1 or "require_contact_with" in t:
        raise RuntimeError("on-table family: its term is not a single object_outside_of with a flat params dict "
                           "(without require_contact_with, which the tooling drops)")
    return t


def default_tolerance(F: dict) -> bool:
    """An object_in_container term that leaves `tolerance` at RoboLab's default."""
    return "object_in_container" in F["conditionals"] and not re.search(r"""["']tolerance["']""", F["terms"])


TOLERANCE_UNUSED = ("RoboLab passes it to `in_opentop_container` "
                    "(`/opt/robolab/robolab/core/task/predicate_logic.py`), which does not use it: \"in\" means that the "
                    "centroid of the object's convex-hull vertices lies within the container's convex hull, open without "
                    "limit along the container's own up axis, with no margin.")
TOLERANCE_TEXT = ("`tolerance` is not set, so it takes `object_in_container`'s default, 0.01 m "
                  "(`/opt/robolab/robolab/core/task/conditionals.py`). " + TOLERANCE_UNUSED)


def set_tolerance(F: dict) -> float | None:
    """The nonzero `tolerance` an object_in_container term sets explicitly (None: unset, zero or not that term)."""
    m = re.search(r"""["']tolerance["']\s*:\s*([0-9.]+)""", F["terms"])
    if re.search(r"""["']tolerance["']""", F["terms"]) and not m:
        raise RuntimeError("a term sets tolerance in a form the generator does not read")
    if "object_in_container" not in F["conditionals"] or not m or float(m.group(1)) == 0.0:
        return None
    return float(m.group(1))


def tolerance_text(F: dict) -> str:
    """What the instruction says about `tolerance`: a margin that the term names but the grader does not apply."""
    if default_tolerance(F):
        return TOLERANCE_TEXT + "\n"
    t = set_tolerance(F)
    return f"The term sets `tolerance` to {t:g} m, but {TOLERANCE_UNUSED}\n" if t is not None else ""


def standard_grading() -> str:
    """The standard mode's pass rule, read from the collect hook (finalize.sh) and the verifier (grade.py)."""
    fin = (HERE / "template/standard/environment/sim/finalize.sh").read_text()
    grade = (HERE / "template/standard/tests/grade.py").read_text()
    n = len(re.findall(r"(?m)^\s*run_replay \d+ \d+ --no-settle\b", fin))
    ok = re.search(r"(?m)^ok = (.*)$", grade)
    need = ('out["replay_success"] = bool(a and a.get("success")) and bool(b and b.get("success"))',
            'out["deterministic"] = bool(a and b) and a["state_sha"] == b["state_sha"]')
    rule = 'bool(d.get("success")) and bool(d.get("replay_success")) and bool(d.get("deterministic")) and not infra'
    if n != 2 or not ok or ok.group(1).strip() != rule or not all(x in fin for x in need):
        raise RuntimeError("standard grader changed: update standard_grading()")
    return ("- **Grading.** When the episode ends, the service's record of it (every control step it ran, including the\n"
            "  hold at the end of your session) is replayed open-loop from the same initial state in two fresh simulator\n"
            "  processes, exactly as recorded; it scores 1 only if the live episode succeeded, both replays succeed and both\n"
            "  end in the same state (equal state hashes), else 0.")


def objects_block(fam: str, F: dict) -> str:
    objs = ", ".join(f"`{o}`" for o in F["objects"] + ["table"])
    cond = ", ".join(f"`{c}`" for c in F["conditionals"])
    note = F["note"].strip()
    head = (f"The scene objects are the env's rigid objects (`s.objects()`: {objs}; see\n"
            f"`/opt/robolab/robolab/tasks/{F['task_file']}`). ")
    if fam in ON_TABLE:
        return (head + f"RoboLab declares the success predicate as the `success` termination term in that file ({cond} in\n"
                f"`/opt/robolab/robolab/core/task/conditionals.py`):\n```python\n{F['terms']}\n```\n"
                f"This task does not grade that term. Its tooling and grader replace it (`ON_TABLE` in `rcb_robolab.py`) with "
                f"RoboLab's own `object_outside_of_and_on_surface` (same file), the same parameters and surface `table`; this "
                f"is the success predicate here (`s.status()`, `s.replay` and the grader all use it), and it also ends the "
                f"episode:\n```python\n{on_table_terms(F)}\n```\n"
                f"Each listed object must be outside the container as above, the gripper must not touch it, and it must also "
                f"rest on the table top ({SUPPORT_SRC}){SUPPORT_RULE}.\n"
                + (f"{note}\n" if note else ""))
    return (head + f"RoboLab's success predicate is the `success` termination\n"
            f"term in that file ({cond} in `/opt/robolab/robolab/core/task/conditionals.py`); it also ends the episode:\n"
            f"```python\n{F['terms']}\n```\n" + tolerance_text(F)
            + (f"{note}\n" if note else ""))


def standard_goal(fam: str, F: dict) -> str:
    """families.json's standard goal, plus the on-table rule of the ON_TABLE families."""
    g = F["standard_goal"].rstrip()
    if fam not in ON_TABLE:
        return g
    objs = re.search(r'"object": \[([^\]]*)\]', F["terms"])
    n = len(re.findall(r'"[^"]+"', objs.group(1))) if objs else 0
    if not n:
        raise RuntimeError(f"{fam}: no object list in its term")
    return g + f" {'It' if n == 1 else 'Each of them'} must also {SUPPORT_TEXT}."


def change_log_1016(fam: str, F: dict, mode: str) -> str:
    """The README Change Log entry of the 2026-10-16 text fixes (instruction audit), with what applies to this task."""
    items = []
    if fam in ON_TABLE:
        items.append("the on-table rule of 2026-10-14 is now stated: the success predicate is RoboLab's "
                     "`object_outside_of_and_on_surface` (surface `table`; the object rests on the table top, held in the air or "
                     "dropped on the floor does not count)" + (", shown next to the quoted upstream `object_outside_of` term "
                                                              "that it replaces" if mode == "privileged" else ""))
    if mode == "privileged":
        if default_tolerance(F):
            items.append("the instruction states `object_in_container`'s default `tolerance` (0.01 m), which "
                         "`in_opentop_container` does not use")
        elif set_tolerance(F) is not None:
            items.append(f"the instruction states that the term's `tolerance` ({set_tolerance(F):g} m) is not used by "
                         "`in_opentop_container` (no margin)")
        items.append("the Tooling comment on `s.reset()` no longer calls it an exact state restore (the Conventions say "
                     "that not every PhysX internal is restored)")
    else:
        items.append("the Rules state the pass rule: two fresh-process replays of the recorded episode, live success, both "
                     "replays successful and both ending in the same state")
        if "neither gripper finger touches it" in F["standard_objects"]:   # the two families that said "with the gripper open"
            items.append("\"with the gripper open\" is now \"and neither gripper finger touches it\" (the term's "
                         "`require_gripper_detached`)")
    body = "; ".join(f"({i}) {t}" for i, t in enumerate(items, 1))
    return (f"- 2026-10-16 (in place: a new DIGEST, PROTOCOL v2.0 §1 and H.8; texts only). From the instruction audit of "
            f"2026-10-16, the instruction now states the rules the grader applies: {body}. The scene, the frozen instance, "
            f"the tooling, the success term and the grader are unchanged, so the task keeps its name and results under the "
            f"2026-10-14 DIGEST are graded the same way.\n")


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

    common = {"AGENT_TIMEOUT_S": str(CUTOFF_SEC), "FAMILY": fam, "SLUG": slug(fam), "PRIV": task_dir(fam, "privileged"), "STD": task_dir(fam, "standard"),
              "SEED": str(F["seed"]), "IMAGE": image, "IMAGE_VERSION": version, "ALLOWED_HOSTS": ALLOWED_HOSTS,
              "CLIENT_IMAGE": CLIENT["CLIENT_IMAGE"].strip()}
    priv = {"GOAL": F["goal"], "GOAL_TOML": toml_str(F["goal"]), "ROBOLAB_TASK": F["robolab_task"], "README_GOAL": F.get("readme_goal", F["goal"]),
            "DIFFICULTY": F["difficulty"], "OBJECTS_BLOCK": objects_block(fam, F), **per_mode("privileged"),
            "CHANGE_LOG_1016": change_log_1016(fam, F, "privileged"),
            "REFERENCE_SOLUTION": reference("privileged", F.get("reference_solution", ""))}
    std = {"INSTANCE_TEXT": toml_str(I["text"]), "STANDARD_GOAL": standard_goal(fam, F), "STANDARD_GRADING": standard_grading(),
           "CHANGE_LOG_1016": change_log_1016(fam, F, "standard"),
           "CHANGE_LOG_EXTRA": "".join(f"- {x}\n" for x in F.get("change_log", [])), "STANDARD_OBJECTS": F["standard_objects"].rstrip() + "\n",
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
