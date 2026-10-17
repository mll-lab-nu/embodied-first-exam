#!/usr/bin/env python3
"""Generate the AM-Bench tasks: tasks/ambench-<task>-fahexa-iNN-<mode> for every frozen instance in scripts/ambench/instances.json
and every mode its `modes` lists (a task's own `modes` overrides the file's: a task graded by its live episode, instance.json
"determinism": "verdict", is standard-only, PROTOCOL §4.8; docs/benchmarks/ambench.md).

    python3 scripts/ambench/mk_tasks.py              # (re)write every AM-Bench task dir; `git diff tasks/` stays empty
    python3 scripts/ambench/mk_tasks.py --check      # write nothing; exit 1 if a task dir differs from the generator's
Then `cd tasks && harbor add --scan .` when a digest changed. Needs only Python 3 (no simulator).

Inputs, all in the repository:
  scripts/ambench/instances.json          per task: the frozen instance (id NN = task iNN), its hashes and its provenance
  scripts/ambench/frozen/<task>-iNN/      instance.json (the environment id, the seed, the start's state hash) and
                                          oracle_actions.npy (the expert's recorded rows, one per control step)
  scripts/ambench/descr/<task>.json       what the task asks and exactly what its check tests, written from the task's code
                                          (summary / scene: both modes; scene_privileged: privileged mode only)
  scripts/ambench/shared/rcb_ambench.py   the tooling (privileged environment/ + tests/, standard environment/sim/)
  scripts/ambench/template/<mode>/        every other task file; a *.tmpl file is filled with the instance's values (@@KEY@@)
  scripts/eai_standard/                   the eai-standard/2.2 layer, copied unchanged, and the standard client (client.env)
  images/ambench/VERSION                  the base image tag
Both twins are written to a scratch directory, passed through scripts/task_conventions.py's normalize() and synced into
tasks/: a task dir holds exactly what the generator writes."""
from __future__ import annotations
import argparse, json, os, pathlib, re, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = ROOT / "scripts/ambench"
LAYER = ROOT / "scripts/eai_standard"
REGISTRY = "ghcr.io/mll-lab-nu"
CLIENT = dict(l.split("=", 1) for l in (LAYER / "client.env").read_text().splitlines() if "=" in l and not l.startswith("#"))
MODES = ("privileged", "standard")
COORD = re.compile(r"\(\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*(?:,\s*-?\d+(?:\.\d+)?\s*)?\)")


VERIFY_REPLAY = ("Graded by the live episode (owner 2026-10-17, board 0151): `success` = the live episode's success, judged by "
                 "the sim service on the episode the agent ran, with no grading replay (until 2026-10-17: live success ∧ two "
                 "fresh-process replays that succeed and agree on the outcome). The live service runs camera-free physics (its "
                 "cameras are drawn by a separate render process), the same computation as a fresh-process replay of its rows.")
VERIFY_VERDICT = ("Graded by the live episode, like every standard task since 2026-10-17 (owner, board 0151), and this one "
                  "before too: GPU PhysX does not replay it bit for bit (measured: the same rows, from identical states and "
                  "identical controller outputs, resolve the first gripper contact differently in fresh processes), so "
                  "`success` = the live episode's success, and no replay runs. The task is standard-only: an open-loop "
                  "trajectory of it cannot be graded reproducibly.")


def toml_str(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def base(task: str, i: int) -> str:
    return f"ambench-{task.replace('_', '-')}-fahexa-i{i:02d}"


def normalizer():
    sys.path.insert(0, str(ROOT / "scripts"))
    from task_conventions import normalize
    return normalize


# The agent's time cutoff per mode (PROTOCOL §2.12): this benchmark's own number, written into every task's `[agent]
# timeout_sec`, the one source; normalize renders from it the instruction's closing `## Time limit`, the README row and
# the sim service's wall clock. To change it (an owner decision; the pull request states old -> new), edit it here and
# regenerate.
CUTOFF_SEC = {"privileged": 3600, "standard": 3600}


def agent_timeout(mode: str) -> int:
    return CUTOFF_SEC[mode]


def fill(text: str, values: dict) -> str:
    for k, v in values.items():
        text = text.replace(f"@@{k}@@", v)
    if "@@" in text:
        raise RuntimeError(f"unfilled placeholder near {text[text.index('@@'):][:40]!r}")
    return text


def num(v) -> str:
    return f"{v:g}" if isinstance(v, float) else str(v)


def plan_instance(task: str, R: dict, version: str, modes) -> dict[str, dict[str, tuple[bytes, int]]]:
    i = int(R["id"])
    D = json.loads((HERE / "descr" / f"{task}.json").read_text())
    fz = HERE / "frozen" / f"{task}-i{i:02d}"
    inst_b = (fz / "instance.json").read_bytes(); I = json.loads(inst_b)
    oracle_b = (fz / "oracle_actions.npy").read_bytes()
    if I["env_id"] != D["env_id"] or I.get("initial_sha") != R["initial_sha"] or int(I["seed"]) != int(R["seed"]):
        raise RuntimeError(f"{fz}: instance.json does not match descr / instances.json (env_id, seed, initial_sha)")
    if any(k in I for k in ("provenance", "expert", "source")) or re.search(rb"scripted|expert|policies", inst_b, re.I):
        raise RuntimeError(f"{fz}: instance.json names its source; provenance belongs in instances.json only (PROTOCOL §2.7)")
    for key in ("summary", "scene", "standard_notes"):
        hits = [m.group(0) for m in COORD.finditer(D[key])]
        if hits:
            raise RuntimeError(f"descr/{task}.json {key}: a world coordinate {hits[:2]} in a text standard mode shows")
    tool = (HERE / "shared/rcb_ambench.py").read_bytes()
    image = f"{REGISTRY}/eai-ambench:{version}"
    ep = float(I["episode_length_s"])
    fails = "".join(f"- {f}\n" for f in D.get("failures") or [])
    fails = ("\nIt also ends, as a failure, when:\n" + fails) if fails else ""
    goals = f"\n**Goal geometry.** {D['goal_fixed']}\n" if D.get("goal_fixed") else ""
    common = {"TITLE": D["title"], "INST": f"i{i:02d}", "PRIV": f"{base(task, i)}-privileged", "STD": f"{base(task, i)}-standard",
              "ENV_ID": I["env_id"], "IMAGE": image, "CLIENT_IMAGE": CLIENT["CLIENT_IMAGE"].strip(), "SEED": str(int(I["seed"])),
              "FAMILY": f"{task}_fahexa", "GOAL_TOML": toml_str("Task: " + D["summary"]), "SUMMARY": D["summary"], "SCENE": D["scene"],
              "GOALS": goals, "SUCCESS": D["success"], "EPISODE_S": num(ep), "EPISODE_ROWS": str(int(round(ep * 120)) - 1),
              # tests/grade.py's per-process limit, max(1800, 1500 + rows / 4) s, four times: two replays, one rerun, the film
              "VERIFIER_TIMEOUT_S": str(int(-(-4 * max(1800.0, 1500.0 + (round(ep * 120) - 1) / 4.0) // 100) * 100)),
              "FAILURES": fails, "README_GOAL": D["summary"], "DIFFICULTY": D["difficulty_note"], "N_ORACLE": str(R["oracle_rows"]),
              "ORACLE_SIM_S": num(round(R["oracle_rows"] / 120, 3)), "ORACLE_SHA": (R.get("oracle_final_sha") or "")[:16],
              "INITIAL_SHA_SHORT": I["initial_sha"][:16], "FROZEN": f"{task}-i{i:02d}", "STANDARD_NOTES": D["standard_notes"],
              "VERIFY": VERIFY_VERDICT if I.get("determinism") == "verdict" else VERIFY_REPLAY}
    # A task whose physics does not replay bit for bit (instance.json "determinism": "verdict") is standard-only: no
    # privileged twin to point at, the live episode decides (PROTOCOL §4.8), and the oracle's rows are the reference rows
    # recorded on the frozen instance (scripts/ambench/instances.json: their end states differ between fresh processes).
    twin = "privileged" in modes
    if (I.get("determinism") == "verdict") == twin:
        raise RuntimeError(f"{task}: a task graded by its live episode (\"determinism\": \"verdict\") is standard-only, and only it")
    priv = f"`{common['PRIV']}`"
    ends = R.get("oracle_end_states") or {}
    common.update({
        "STD_INTRO": (f"Standard-mode twin of {priv} (the same frozen instance: " if twin else
                      "Standard-only task (no privileged twin: its physics does not replay bit for bit, so an open-loop trajectory "
                      "of it cannot be graded reproducibly; the frozen instance: "),
        "TWIN_ROW": (priv if twin else
                     "— (none: standard only, graded by the live episode; its physics does not replay bit for bit, PROTOCOL §4.8)"),
        "STD_COMPARE": (" Compare against the privileged task to measure the cost of losing\nresets and privileged state." if twin else ""),
        "STD_DIFFICULTY": (f"That of {priv} (its README), without resets, object poses or the success signal: {D['standard_notes']}" if twin else
                           f"{D['difficulty_note']} Here without resets, object poses or the success signal: {D['standard_notes']}"),
        "REF_ROWS": "the privileged oracle's rows" if twin else "the reference rows",
        "ORACLE_END": (f"the live\nepisode ended in the privileged oracle's end state (hash `{common['ORACLE_SHA']}`; under the "
                        f"earlier rule both replays did too)." if twin else
                       f"the reference rows succeed in every fresh process measured but do not end in the same state "
                       f"({len(ends)} different end states in {sum(ends.values())} replays): only the outcome is reproducible, which is "
                       f"why the live episode decides."),
        "RESUME_CLASS": ("`approx` (GPU PhysX replays the journal to the checkpointed state almost always; a rare race can "
                         "leave the last bits different, so a resume's deviation is recorded, `resume_state_mismatch`, and the "
                         "episode continues; the live state after it is graded)" if twin else
                         "`approx` (the physics does not replay bit for bit: a resume's deviation from the "
                         "checkpointed state is recorded, `resume_state_mismatch`, and the live state after it is graded)"),
        "RESUME_STATE": ("the state after the last call it completed (to the last bits: a rare GPU race\n  can leave those "
                         "different)" if twin else
                         "the state after the last call it completed (as closely as this task's physics\n  allows: it does not "
                         "replay bit for bit)"),
        "TOML_INSTANCE": ("on the same frozen instance as the privileged task." if twin else
                          "on its frozen instance; standard only, no privileged twin."),
        "TOML_GRADING": ("the sim service records the episode as a trajectory and grades the live episode." if twin else
                         "the sim service records the episode and grades it as it happened live (the physics does not replay "
                         "bit for bit)."),
    })
    texts = {"task_text": f"{D['title']}: {D['summary']} Success: {D['success']}" + (f" Goal geometry: {D['goal_fixed']}" if D.get("goal_fixed") else ""),
             "episode": (f"one episode, no reset: it ends at the first control step where AM-Bench's success check holds, when the task's "
                         f"episode length of {num(ep)} s of simulated time runs out (AM-Bench's time-out, at control step {int(round(ep * 120)) - 1}), when your time is up, "
                         f"or on a simulator error; the simulated clock advances only with the control steps you run")}
    out: dict[str, dict[str, tuple[bytes, int]]] = {}
    for mode in modes:
        common["AGENT_TIMEOUT_S"] = str(agent_timeout(mode))
        extra = ({"SCENE_PRIVILEGED": D["scene_privileged"]} if mode == "privileged" else
                 {"SUCCESS": D["success_standard"]} if "success_standard" in D else {})   # no privileged API names there
        files: dict[str, tuple[bytes, int]] = {}
        tdir = HERE / "template" / mode
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
            for rel in ("environment/rcb_ambench.py", "tests/rcb_ambench.py"):
                files[rel] = (tool, 0o644)
            for rel in ("environment/instance.json", "tests/instance.json"):
                files[rel] = (inst_b, 0o644)
            files["solution/oracle_actions.npy"] = (oracle_b, 0o644)
        else:
            files["environment/sim/rcb_ambench.py"] = (tool, 0o644)
            files["environment/sim/instance.json"] = (inst_b, 0o644)
            files["environment/sim/texts.json"] = ((json.dumps(texts, indent=1, ensure_ascii=False) + "\n").encode(), 0o644)
            for rel, src in (("environment/rcb_client.py", "rcb_client.py"), ("environment/rcb1.py", "rcb1.py"),
                             ("environment/sim/rcb_limited.py", "rcb_limited.py"), ("environment/sim/rcb1.py", "rcb1.py"),
                             ("environment/sim/run.sh", "run.sh")):
                files[rel] = ((LAYER / src).read_bytes(), 0o755 if rel.endswith(".sh") else 0o644)
            req = CLIENT.get("CLIENT_REQUIREMENTS", "client-requirements.txt").strip()
            files["environment/client-requirements.txt"] = ((LAYER / req).read_bytes(), 0o644)
            files["solution/oracle_qpos.npy"] = (oracle_b, 0o644)
            files["solution/oracle_meta.json"] = (json.dumps({"K": 1, "interpolate": "hold", "source": common["REF_ROWS"]}, indent=1).encode() + b"\n", 0o644)
        out[f"{base(task, i)}-{mode}"] = files
    return out


def normalized(planned, normalize):
    out = {}
    with tempfile.TemporaryDirectory(prefix="ambench_mk_") as td:
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
    a = ap.parse_args()
    reg = json.loads((HERE / "instances.json").read_text())
    modes = tuple(reg.get("modes", MODES))
    version = (ROOT / "images/ambench/VERSION").read_text().strip()
    normalize = normalizer()
    diffs, made = [], set()
    for task in sorted(reg["tasks"]):
        tmodes = tuple(reg["tasks"][task].get("modes", modes))     # a task graded by verdict (PROTOCOL §4.8) is standard-only
        for name, files in normalized(plan_instance(task, reg["tasks"][task], version, tmodes), normalize).items():
            made.add(name); diffs += sync(ROOT / "tasks" / name, files, a.check)
    for t in sorted((ROOT / "tasks").glob("ambench-*")):
        if t.is_dir() and t.name not in made:
            diffs.append(f"stale  {t.name} (not in instances.json)")
    for d in diffs:
        print(d)
    print(f"{'checked' if a.check else 'generated'} {len(made)} AM-Bench task dirs: {len(diffs)} difference(s)")
    return 1 if (a.check and diffs) else 0


if __name__ == "__main__":
    sys.exit(main())
