"""Export the privileged twins of the First Exam matches (tools/fullsim/sports/<sport>.py), natively or into a First
Exam checkout (with a self-contained generator: scripts/roboolympics/privileged/generate.py).

    python -m tools.fullsim.export --sport badminton --out /tmp/priv-tasks          # native (our sim trees)
    python -m tools.fullsim.export --sport badminton --hub /path/to/robot_coding_bench   # install + render upstream
    python3 scripts/roboolympics/privileged/generate.py [--sport S] [--check]          # upstream, from the twins' sims
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

UPSTREAM = True  # True in the copy installed upstream (scripts/roboolympics/privileged/generate.py)
ROOT = Path(__file__).resolve().parents[3 if UPSTREAM else 2]
FULLSIM = Path(__file__).resolve().parent / "tools/fullsim" if UPSTREAM else Path(__file__).resolve().parent
sys.path.insert(0, str(FULLSIM.parents[1]))  # `tools.fullsim` (upstream: a copy next to this generator)
FROZEN = "0d7f680cc04918f419230588732aedbb9ccdc900"
INSTANCE_FILE = "match_instance.json"  # not instance.json: the twin's frozen instance is its sim tree + seed + level
TEMPLATES = FULLSIM / "harbor"
RUNTIME = ("__init__.py", "adapter.py", "session.py", "program.py", "worker.py", "formal.py")
ALLOWLIST = [
    "chatgpt.com",
    "*.chatgpt.com",
    "auth.openai.com",
    "api.openai.com",
    "*.openai.com",
    "api.anthropic.com",
    "*.anthropic.com",
    "openrouter.ai",
    "*.openai.azure.com",
    "*.cognitiveservices.azure.com",
    "pypi.org",
    "files.pythonhosted.org",
    "deb.debian.org",
    "security.debian.org",
    "archive.ubuntu.com",
    "security.ubuntu.com",
    "snapshot.ubuntu.com",
]
URL = re.compile(r"https?://\S+?(?=[\s\"',)]|$)")
PUBLIC_DROP = ("renderers/presentation",)  # the camera renderer's asset download manifest: never used without cameras
TEXT = (".toml", ".json", ".md", ".py", ".txt", ".xml")


def exported():
    """Every adapter whose EXPORT is not False (table tennis: tools/tt_fullsim, PR #154)."""
    import pkgutil

    names = sorted(m.name for m in pkgutil.iter_modules([str(FULLSIM / "sports")]))
    return [n for n in names if getattr(adapter(n), "EXPORT", True)]


def solutions():
    return importlib.import_module("tools.fullsim.solutions").SOLUTIONS


class _Solutions(dict):
    def __missing__(self, sport):
        return solutions()[sport]


SOLUTIONS = _Solutions()


def adapter(sport):
    return importlib.import_module("tools.fullsim.adapter").load(sport)


def instances(ad):
    from_twin = {k: dict(v) for k, v in ad.INSTANCES.items()}
    return [(inst, d["level"], d["seed"]) for inst, d in from_twin.items()]


def task_name(ad, inst):
    return f"roboolympics-{ad.FAMILY}-{inst}-privileged"


def twin_name(ad, inst):
    return f"roboolympics-{ad.FAMILY}-{inst}-standard-realtime"


def source_for(ad, inst):
    """The frozen simulator tree a twin is built from (upstream: the standard-realtime twin's own environment/sim)."""
    if UPSTREAM:
        return ROOT / "tasks" / twin_name(ad, inst) / "environment/sim"
    return ROOT / "tasks" / ad.SOURCE_TASK / "environment/sim"


def repo_file(ad, inst, rel):
    """A repository file the generator copies (an oracle's helper such as sports/<sport>/builtin_players.py)."""
    if not UPSTREAM:
        return ROOT / rel
    if rel.startswith(f"sports/{ad.SPORT}/"):
        return source_for(ad, inst) / "sport" / rel[len(f"sports/{ad.SPORT}/") :]
    return FULLSIM.parents[1] / rel if rel.startswith("tools/fullsim/") else ROOT / rel


def copy_tree(src, dst):
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "lowlevel"))


def public_edit(ad, rel, data):
    """The agent's copy of sports/<sport>/<rel> (bytes): the adapter's PUBLIC_EDITS, {rel: [(old, new), ...]}; an old of
    the form ("<cut>", marker) cuts the file from the line that holds `marker` (the #282 review, H.2: no reference
    player or reference level in the agent's copy)."""
    edits = ad.PUBLIC_EDITS.get(rel)
    if not edits:
        return data
    text = data.decode()
    for old, new in edits:
        if isinstance(old, tuple):
            at = text.index(old[1])
            text = text[: text.rindex("\n", 0, at) + 1] + new
        else:
            if text.count(old) != 1:
                raise SystemExit(f"{ad.SPORT}: PUBLIC_EDITS {rel}: {old[:60]!r} is not in the twin's file exactly once")
            text = text.replace(old, new)
    return text.encode()


def public_bytes(path, data=None):
    """A file of the twin's simulator as the public copies hold it (scrub_public)."""
    data = path.read_bytes() if data is None else data
    if path.suffix in TEXT:
        text = data.decode(errors="surrogateescape")
        data = URL.sub("<link in the trusted copy>", text).encode(errors="surrogateescape")
    return data


def scrub_public(dst):
    """The agent's copies hold no URL (PROTOCOL H.2, ci_checks/check-agent-pointers.py): citations keep their text,
    without the link; the renderer's asset manifest (a download pointer, unused here) is left out. The trusted copy
    stays byte-identical to the twin's simulator."""
    for rel in PUBLIC_DROP:
        shutil.rmtree(dst / rel, ignore_errors=True)
    for f in sorted(dst.rglob("*")):
        if f.is_file() and f.suffix in TEXT:
            data = public_bytes(f)
            if data != f.read_bytes():
                f.write_bytes(data)


def public_adapter(src):
    """The agent's copy of tools/fullsim/sports/<sport>.py (text): without the adapter's PUBLIC_DROP_FILES / PUBLIC_EDITS
    assignments and the comment block above them (#282 review, H.2: they spell out what the public copy leaves out, e.g.
    the reference level's parameters); nothing at run time reads them (the generator does, from its own copy)."""
    import ast

    text = src.read_text()
    lines = text.splitlines(keepends=True)
    cut = set()
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") in ("PUBLIC_DROP_FILES", "PUBLIC_EDITS")
                                                for t in node.targets):
            first = node.lineno - 1
            while first > 0 and lines[first - 1].lstrip().startswith("#"):
                first -= 1
            cut.update(range(first, node.end_lineno))
    return "".join(ln for i, ln in enumerate(lines) if i not in cut)


def bundle(dst, ad, inst, *, public):
    source = source_for(ad, inst)
    dst.mkdir(parents=True)
    for name in ("core", "bodies", "renderers", "skilleval", "metering", "spectator"):
        if (source / name).exists():
            copy_tree(source / name, dst / name)
    copy_tree(source / "sport", dst / "sports" / ad.SPORT)  # the repository layout the Session expects
    if public:
        for rel in ad.PUBLIC_DROP_FILES:  # the camera-only reference player: not in the agent's copy (H.2)
            (dst / "sports" / ad.SPORT / rel).unlink(missing_ok=True)
        for rel in ad.PUBLIC_EDITS:  # a reference player or level inside a file the simulator needs (H.2)
            f = dst / "sports" / ad.SPORT / rel
            f.write_bytes(public_edit(ad, rel, f.read_bytes()))
        scrub_public(dst)
    target = dst / "tools/fullsim"
    (target / "sports").mkdir(parents=True)
    (dst / "tools/__init__.py").write_text("")
    for name in RUNTIME:
        shutil.copy2(FULLSIM / name, target / name)
    shutil.copy2(FULLSIM / "sports/__init__.py", target / "sports/__init__.py")
    if public:
        (target / "sports" / f"{ad.SPORT}.py").write_text(public_adapter(FULLSIM / "sports" / f"{ad.SPORT}.py"))
    else:
        shutil.copy2(FULLSIM / "sports" / f"{ad.SPORT}.py", target / "sports" / f"{ad.SPORT}.py")


ORACLE_EVIDENCE = (
    "full-state reference program (solution/): the camera-only reference player's planner fed the true state; its "
    "results on this instance and across the levels are in the RoboOlympics privileged report (tools/fullsim/calibrate.py)"
)


def resources(ad):
    r = {
        "min_cpus": 4.0,
        "min_memory_gb": 6.0,
        "verifier_min_cpus": 4.0,
        "verifier_min_memory_gb": 8.0,
        "cpus": 4,  # the agent's and the verifier's containers ([environment], [verifier.environment])
        "memory_mb": 8192,
        **ad.RESOURCES,
    }
    # the verifier plays a wall-clock match (#282 review, decision 1): its CPUs are pinned, the minimum = the cap
    r["verifier_min_cpus"] = float(r["cpus"])
    return r


def task_toml(ad, inst, level, seed):
    name, twin, r = task_name(ad, inst), twin_name(ad, inst), resources(ad)
    return f'''schema_version = "1.3"
artifacts = ["/app/output/"]
[task]
name = "robot-coding-bench/{name}"
description = "PRIVILEGED (RoboOlympics / Embodied Agent Olympics): {ad.DESCRIPTION or ad.SPORT}, one match against the scripted opponent at level {level} on the frozen instance of {twin} (seed {seed}, S = {ad.SLOWDOWN}). Full simulator in development (read and change any state, reset the whole match); the deliverable is a closed-loop Python program that plays a fresh unmodified match in the verifier, on the original S = {ad.SLOWDOWN} clock, seeing the full state instead of camera images."
authors = [{{ name = "RoboOlympics (CHIGUI0)" }}]
keywords = ["robotics", "mujoco", "fullsim", "policy", "{ad.SPORT}"]
[metadata]
author_name = "RoboOlympics"
task_type = "policy"
simulator = "mujoco"
robot = "{getattr(ad, "ROBOT", "franka-panda")}"
family = "{getattr(ad, "METADATA_FAMILY", None) or ad.FAMILY.replace("-", "_")}"
mode = "privileged"
dynamics = "dynamic"
verifier_wall_clock = true
instance_seed = {seed}
opponent_level = {level}
slowdown = {ad.SLOWDOWN}
source_commits = ["{FROZEN[:12]}"]
source_task = "roboolympics/{ad.SOURCE_TASK}"
exporter = "roboolympics tools.fullsim.export"
official = false
expert_time_estimate_hours = 1.0
oracle = "partial"
oracle_evidence = "{SOLUTIONS[ad.SPORT]["evidence"] or ORACLE_EVIDENCE}; not reproduced in this repository: the owner waived the oracle runs on 2026-10-17 (validated = false)"
validated = false
[metadata.seeds]
default = {seed}
allowed = [{seed}]
oracle = [{seed}]
[metadata.resources]
min_cpus = {r["min_cpus"]}
min_memory_gb = {r["min_memory_gb"]}
min_gpu_memory_gb = 0.0
gpu_required = false
gpu_class = "none"
verifier_min_cpus = {r["verifier_min_cpus"]}
verifier_min_memory_gb = {r["verifier_min_memory_gb"]}
verifier_min_gpu_memory_gb = 0.0
measured = "author estimate; CPU-only frozen MuJoCo, full simulator development and original realtime formal service"
[agent]
timeout_sec = {float(ad.CUTOFF_S)}
network_mode = "allowlist"
allowed_hosts = {json.dumps(ALLOWLIST)}
[environment]
build_timeout_sec = 1800.0
cpus = {r["cpus"]}
memory_mb = {r["memory_mb"]}
[verifier]
timeout_sec = {float(ad.VERIFIER_TIMEOUT_S)}
environment_mode = "separate"
network_mode = "no-network"
[verifier.environment]
build_timeout_sec = 1800.0
cpus = {r["cpus"]}
memory_mb = {r["memory_mb"]}
'''


def fill(text, ad, inst, level, seed):
    for k, v in {
        "@SPORT@": ad.SPORT,
        "@LEVEL@": level,
        "@SEED@": seed,
        "@TWIN@": twin_name(ad, inst),
        "@SLOWDOWN@": ad.SLOWDOWN,
        "@EVERY@": ad.EVERY,
        "@MAX_COMMANDS@": ad.MAX_COMMANDS,
        "@READY@": ad.READY_TIMEOUT_S,
        "@MATCH_WALL_S@": ad.MATCH_WALL_S,
        "@TRUTH_DOC@": ad.TRUTH_DOC.strip(),
        "@NOTES_DOC@": ad.NOTES_DOC.strip(),
        "@IMAGE@": ad.IMAGE,
    }.items():
        text = text.replace(k, str(v))
    return text


def _twin_s(ad):
    t = getattr(ad, "TWIN_SLOWDOWN", ad.SLOWDOWN)
    return "" if t == ad.SLOWDOWN else f" (the twin's world runs at 1/{t}: this formal match is shorter in wall time)"


def instruction(ad, inst, level, seed):
    return f"""# Full-simulator {ad.SPORT}: develop a program against level {level}

Win one complete match against the frozen sport's scripted level-{level} opponent, seed {seed}: the same frozen
instance as `{twin_name(ad, inst)}` (its standard-realtime twin; there you see only camera images). The robot, the actions,
the rules, the limits and the opponent are unchanged; the world runs at 1/{ad.SLOWDOWN} of real speed{_twin_s(ad)}.

## Development and deliverable
`from tools.fullsim.session import Session`; `Session("{ad.SPORT}", level={level}, seed={seed})` gives `state()`,
`world`, `spec()`, `act(command)`, `step(n)`, `ready()` and `reset()`. The simulator and its source are at
`/opt/fullsim`. Reset rebuilds the WHOLE same-seed match. You may inspect and change private worlds and develop and
search with repeated resets within your resource and time limits; nothing of this reaches the formal match.
Read `/opt/fullsim/README.md` for the program API, the `truth` fields, the units and the self-test.

Leave `/app/output/policy/program.py` and any helper or data files in that directory (512 regular files, 32 MiB;
no links or special files). Define `make_policy(config)` returning an object with `act(view)`; it lives for the whole
match. `view` holds `state` (the twin's observation fields), `truth` (the full current state), `scores`. Return one
original action, a list of at most {ad.MAX_COMMANDS}, `{{"type": "ready"}}` during a review, or None. No model or
API calls during the formal evaluation. Submit executable code, not a recorded trajectory or a claimed score; save a
valid program early and improve it.

## Formal evaluation
A separate verifier without network runs your final program as an unprivileged process against a fresh, unmodified
match; your program can read a public, read-only copy of the simulator (`/opt/dev`, the same as `/opt/fullsim`) for its
own predictions, never the trusted copy that runs the match, the referee or the logs.
There is no formal reset. The original realtime clock runs at S = {ad.SLOWDOWN} while your program computes; each
review (after a point, a goal or another stoppage) freezes the world (at most {ad.READY_TIMEOUT_S} s). The formal match
has {ad.MATCH_WALL_S} s of wall time.
The service replays the trusted journal once in a fresh process; success is a complete win by the original referee
with a matching replay. The match runs on the wall clock, so, as in the standard-realtime twin, the verifier's speed
matters: it runs on {resources(ad)["cpus"]} pinned CPUs. This fixed instance does not measure generalization to other instances.
"""


def write_task(out, ad, inst, level, seed, hub=None):
    name = task_name(ad, inst)
    dst = out / name
    if dst.exists():
        shutil.rmtree(dst)
    env, tests, solution = dst / "environment", dst / "tests", dst / "solution"
    env.mkdir(parents=True)
    tests.mkdir()
    solution.mkdir()
    bundle(env / "fullsim", ad, inst, public=True)
    bundle(tests / "trusted", ad, inst, public=False)
    copy_tree(env / "fullsim", tests / "dev")  # the program's public copy in the verifier (not the trusted tree)
    base = fill((TEMPLATES / "base.Dockerfile").read_text(), ad, inst, level, seed)
    (env / "Dockerfile").write_text(
        base
        + """COPY fullsim/ /opt/fullsim/
ENV PYTHONPATH=/opt/fullsim
WORKDIR /app
RUN mkdir -p /app/output && chmod -R a+rX /opt/fullsim
"""
    )
    readme = fill((TEMPLATES / "README.md").read_text(), ad, inst, level, seed)
    for root in (env / "fullsim", tests / "dev"):
        (root / "README.md").write_text(readme)
    (tests / "Dockerfile").write_text(
        base
        + """COPY trusted/ /opt/trusted/
COPY dev/ /opt/dev/
COPY grade.py match_instance.json test.sh /tests/
RUN chmod 700 /opt/trusted && chmod -R a-w /opt/dev && chmod -R a+rX /opt/dev \\
    && chmod +x /tests/test.sh && mkdir -p /logs/verifier && chmod 700 /logs/verifier
WORKDIR /opt/trusted
"""
    )
    shutil.copy2(TEMPLATES / "grade.py", tests / "grade.py")
    inst_json = json.dumps({"sport": ad.SPORT, "level": level, "seed": seed, "slowdown": ad.SLOWDOWN}) + "\n"
    (tests / INSTANCE_FILE).write_text(inst_json)
    (env / INSTANCE_FILE).write_text(inst_json)
    (tests / "test.sh").write_text("""#!/bin/bash
set -eu
mkdir -p /logs/verifier
rm -rf /logs/verifier/* /logs/verifier/.[!.]*
chmod 755 /logs/verifier
python /tests/grade.py > /logs/verifier/grade.log 2>&1
""")
    (tests / "test.sh").chmod(0o755)
    # The oracle lives only in solution/, never in the agent's copy of the simulator.
    sol = SOLUTIONS[ad.SPORT]
    shutil.copy2(repo_file(ad, inst, sol["program"]), solution / "program.py")
    for rel in sol["files"]:
        shutil.copy2(repo_file(ad, inst, rel), solution / Path(rel).name)
    files = " ".join(["/solution/program.py"] + [f"/solution/{Path(r).name}" for r in sol["files"]])
    (solution / "solve.sh").write_text(f"""#!/bin/bash
set -eu
mkdir -p /app/output/policy
cp {files} /app/output/policy/
""")
    (solution / "solve.sh").chmod(0o755)
    (dst / "task.toml").write_text(task_toml(ad, inst, level, seed))
    (dst / "instruction.md").write_text(instruction(ad, inst, level, seed))
    (dst / "README.md").write_text(f"""# {name}

## Task
The privileged twin of `{twin_name(ad, inst)}`: {ad.DESCRIPTION or ad.SPORT}; level {level}, seed {seed}, S = {ad.SLOWDOWN}.

## Difficulty
Same frozen sport and instance as the twin; full-simulator development and the full state instead of camera images.

## Reference solution
`solution/solve.sh` submits the full-state reference program (the camera-only reference player's planner fed the true
state).

## Verification
Separate verifier without network; root-owned trusted source, the program as nobody (a process limit; every process
of nobody is ended with kill(-1) before the verdict, and a survivor is the program's 0, never a retry), the original
realtime service on the wall clock at S = {ad.SLOWDOWN} (the verdict depends on the host's speed, as in the
standard-realtime twin: the verifier runs on {resources(ad)["cpus"]} pinned CPUs, part of the configuration key), one
fresh journal replay, then the replay video (replay.mp4) from the record.

## Development copy
The privileged setting: the full simulator during development (`/opt/fullsim`, read and change any state, reset the
whole match). In the verifier the program may read the same public copy read-only (`/opt/dev`); the trusted copy that
runs the formal match is root-only. The public copies hold no reference player and no reference level (H.2).
""")
    if hub:
        sys.path.insert(0, str(hub / "scripts"))
        importlib.import_module("task_conventions").normalize(dst)
    return name


def build(out, sports, hub=None):
    names = []
    for sport in sports:
        ad = adapter(sport)
        for inst, level, seed in instances(ad):
            names.append(write_task(out, ad, inst, level, seed, hub))
    return names


def snapshot(root):
    return {
        str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mode & 0o777)
        for p in sorted(root.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts
    }


def twin_identity(tasks, sports):
    """PROTOCOL H.7: the privileged twin runs its standard-realtime twin's frozen simulator (environment/sim) byte for
    byte (the trusted copy; the public copies as scrub_public leaves them) and the same seed, level and S."""
    for sport in sports:
        ad = adapter(sport)
        for inst, level, seed in instances(ad):
            name, twin = task_name(ad, inst), twin_name(ad, inst)
            sim = tasks / twin / "environment/sim"
            compose = (tasks / twin / "environment/docker-compose.yaml").read_text()
            for key, value in (("RO_SEED", seed), ("RO_LEVEL", level), ("RO_SLOWDOWN", getattr(ad, "TWIN_SLOWDOWN", ad.SLOWDOWN)),
                               ("RO_FORMAT", ad.FORMAT), ("RCB_ACTION_LEVEL", ad.ACTION_LEVEL),
                               ("READY_TIMEOUT_S", ad.READY_TIMEOUT_S)):
                if f'{key}: "{value}"' not in compose:
                    raise SystemExit(f"{name}: twin {twin} does not run {key} = {value}")
            for copy in ("tests/trusted", "tests/dev", "environment/fullsim"):
                root = tasks / name / copy
                public = copy != "tests/trusted"
                for f in sorted(p for p in sim.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
                    rel = f.relative_to(sim)
                    sub = Path("sports", ad.SPORT, *rel.parts[1:]) if rel.parts[0] == "sport" else rel
                    mine = root / sub
                    dropped = rel.parts[0] == "sport" and Path(*rel.parts[1:]).as_posix() in ad.PUBLIC_DROP_FILES
                    if "lowlevel" in rel.parts or (
                        public and (dropped or any(rel.as_posix().startswith(d) for d in PUBLIC_DROP))
                    ):
                        continue
                    in_sport = Path(*rel.parts[1:]).as_posix() if rel.parts[0] == "sport" else None
                    want = (public_bytes(f, public_edit(ad, in_sport, f.read_bytes()) if in_sport else None) if public
                            else f.read_bytes())
                    if not mine.is_file() or mine.read_bytes() != want:
                        raise SystemExit(f"{name}/{copy}: {sub} differs from {twin}'s sim/{rel}")


UPSTREAM_STUB = ('\ndef install_upstream(hub):\n    """Only the native generator (RoboOlympics tools/fullsim/export.py) installs; this copy renders and checks."""\n'
                 '    raise SystemExit("install from RoboOlympics: python -m tools.fullsim.export --hub <checkout>")\n\n')


def install_upstream(hub):
    """Only the native generator (RoboOlympics tools/fullsim/export.py) installs; this copy renders and checks."""
    raise SystemExit("install from RoboOlympics: python -m tools.fullsim.export --hub <checkout>")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sport", action="append", help="default: every exported sport (exported())")
    p.add_argument("--out", type=Path)
    p.add_argument("--hub", type=Path, default=ROOT if UPSTREAM else None)
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    sports = args.sport or exported()
    if not args.out and not args.hub:
        p.error("provide --out or --hub")
    out = args.out or args.hub / "tasks"
    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            for sport in sports:  # normalize renders the README's Twin row from the sibling directory
                ad = adapter(sport)
                for inst, _, _ in instances(ad):
                    if (out / twin_name(ad, inst)).is_dir():
                        (Path(tmp) / twin_name(ad, inst)).symlink_to(out / twin_name(ad, inst))
            names = build(Path(tmp), sports, args.hub)
            for name in names:
                if snapshot(Path(tmp) / name) != snapshot(out / name):
                    raise SystemExit(f"generated task differs: {name}")
        if UPSTREAM:
            twin_identity(out, sports)
        print(f"privileged twins match the generator ({len(names)} task(s)); trusted simulators byte-identical")
    elif args.hub and not UPSTREAM:  # install the self-contained generator; it renders from the twins' own sims
        install_upstream(args.hub)
        cmd = [sys.executable, str(args.hub / "scripts/roboolympics/privileged/generate.py")]
        for s in sports:
            cmd += ["--sport", s]
        subprocess.run(cmd, check=True)
    else:
        print("wrote " + ", ".join(build(out, sports, args.hub)))


if __name__ == "__main__":
    main()
