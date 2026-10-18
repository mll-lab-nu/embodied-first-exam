"""Deterministic native + First Exam fullsim policy task exporter.

python -m tools.tt_fullsim.export --out /tmp/fullsim-tasks
python -m tools.tt_fullsim.export --hub /path/to/robot_coding_bench
python -m tools.tt_fullsim.export --hub /path/to/robot_coding_bench --check
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FROZEN = "0d7f680cc04918f419230588732aedbb9ccdc900"
# The privileged twins of the exported standard-realtime matches (PROTOCOL H.7): same instance (seed, opponent level,
# frozen simulator source), same seeds, same cutoff. (instance id, opponent level, seed)
INSTANCES = (("i01", 2, 22), ("i02", 3, 12))
TASKS = tuple((level, f"roboolympics-tabletennis-match-{i}-privileged") for i, level, _ in INSTANCES)
SEEDS = {f"roboolympics-tabletennis-match-{i}-privileged": seed for i, _, seed in INSTANCES}
TWINS = {
    f"roboolympics-tabletennis-match-{i}-privileged": f"roboolympics-tabletennis-match-{i}-standard-realtime"
    for i, _, _ in INSTANCES
}
SOURCE_TEMPLATE = "tasks/@TWIN@/environment/sim"
INSTANCE_FILE = "match_instance.json"  # not instance.json: the twin's frozen instance is its sim tree + seed + level
# The formal match ends as in the standard-realtime twin (#282 decision 5): when it is over, or, unfinished and not won,
# at the twin's own cutoff (its agent session, RCB_WALL_CLOCK_S). The verifier's timeout holds that bound, the
# service's replay and verdict (650 s), the replay video (VIDEO_S), the program's load and the monitor's seal.
WALL_LIMIT_S = 7200
VIDEO_S = 1800
VERIFIER_TIMEOUT_S = WALL_LIMIT_S + 650 + VIDEO_S + 30 + 120 + 200
VERIFIER_CPUS = 4  # pinned: the minimum is the cap (#282 decision 1: a live match's verdict depends on the host's speed)


def source_for(name):
    """The frozen simulator tree a twin is built from (upstream: the standard-realtime twin's own environment/sim)."""
    return ROOT / SOURCE_TEMPLATE.replace("@TWIN@", TWINS[name])


SOURCE = source_for(TASKS[0][1])
TEMPLATES = Path(__file__).resolve().parent / "templates"
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


def copy_tree(src, dst):
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "lowlevel"))


URL = re.compile(r"https?://\S+?(?=[\s\"',)]|$)")
PUBLIC_DROP = ("renderers/presentation",)  # the camera renderer's asset download manifest: never used without cameras


def scrub_public(dst):
    """The agent's copies hold no URL (PROTOCOL H.2, ci_checks/check-agent-pointers.py): the robot limits' citations
    keep their text, without the link; the renderer's asset manifest (a download pointer, unused here) is left out. The
    trusted copy stays byte-identical to the twin's simulator."""
    for rel in PUBLIC_DROP:
        shutil.rmtree(dst / rel, ignore_errors=True)
    for f in sorted(dst.rglob("*")):
        if f.is_file() and f.suffix in (".toml", ".json", ".md", ".py", ".txt", ".xml"):
            text = f.read_text(errors="surrogateescape")
            new = URL.sub("<link in the trusted copy>", text)
            if new != text:
                f.write_text(new, errors="surrogateescape")
    return dst


def public_bytes(path):
    """A file of the twin's simulator as the public copies hold it (scrub_public)."""
    data = path.read_bytes()
    if path.suffix in (".toml", ".json", ".md", ".py", ".txt", ".xml"):
        text = data.decode(errors="surrogateescape")
        data = URL.sub("<link in the trusted copy>", text).encode(errors="surrogateescape")
    return data


def bundle(dst, *, public, source=None):
    SOURCE = source or globals()["SOURCE"]
    dst.mkdir(parents=True)
    for name in ("core", "bodies", "renderers", "skilleval", "metering", "spectator"):
        if (SOURCE / name).exists():
            copy_tree(SOURCE / name, dst / name)
    # Match the repository layout expected by the development Session; bytes remain unchanged.
    copy_tree(SOURCE / "sport", dst / "sports/tabletennis")
    if public:
        (dst / "sports/tabletennis/builtin_players.py").unlink(missing_ok=True)
        scrub_public(dst)
    target = dst / "tools/tt_fullsim"
    target.mkdir(parents=True)
    (dst / "tools/__init__.py").write_text("")
    for name in ("__init__.py", "session.py", "runner.py", "worker.py", "formal.py"):
        shutil.copy2(Path(__file__).resolve().parent / "runtime" / name, target / name)
    files = {
        str(p.relative_to(dst)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(dst.rglob("*"))
        if p.is_file()
    }
    (dst / "bundle.sha256.json").write_text(json.dumps(files, indent=2, sort_keys=True) + "\n")


def task_toml(level, name):
    seed = SEEDS[name]
    return f'''schema_version = "1.3"
artifacts = ["/app/output/"]
[task]
name = "robot-coding-bench/{name}"
description = "PRIVILEGED (RoboOlympics / Embodied Agent Olympics): table tennis, one match against the scripted opponent at level {level} on the frozen instance of {TWINS[name]} (seed {seed}). Full simulator in development (read and change any state, reset the whole match); the deliverable is a closed-loop Python program that plays a fresh unmodified match in the verifier, on the original S = 10 clock, seeing the full state instead of camera images."
authors = [{{ name = "RoboOlympics (CHIGUI0)" }}]
keywords = ["robotics", "mujoco", "fullsim", "policy", "tabletennis"]
[metadata]
author_name = "RoboOlympics"
task_type = "policy"
simulator = "mujoco"
robot = "franka-panda"
family = "tabletennis_match"
mode = "privileged"
dynamics = "dynamic"
verifier_wall_clock = true
instance_seed = {seed}
opponent_level = {level}
slowdown = 10
revision = "wallclock-15+duel-wallclock-12+low-inloop-1+core-0.2"
source_commits = ["{FROZEN[:12]}"]
source_task = "roboolympics/tabletennis-match-wallclock-program-standard"
exporter = "roboolympics tools.tt_fullsim.export"
official = false
expert_time_estimate_hours = 1.0
oracle = "partial"
oracle_evidence = "full-state reference program (solution/): the camera-only reference player's serve and stroke planner fed the true ball state; its wins on this instance and across levels 1-4 are in the RoboOlympics privileged report (tools/tt_fullsim/calibrate.py); not reproduced in this repository: the owner waived the oracle runs on 2026-10-17 (validated = false)"
validated = false
[metadata.seeds]
default = {seed}
allowed = [{seed}]
oracle = [{seed}]
[metadata.resources]
min_cpus = 4.0
min_memory_gb = 8.0
min_gpu_memory_gb = 0.0
gpu_required = false
gpu_class = "none"
verifier_min_cpus = {VERIFIER_CPUS}.0
verifier_min_memory_gb = 8.0
verifier_min_gpu_memory_gb = 0.0
measured = "author estimate; CPU-only frozen MuJoCo, full simulator development and original realtime formal service"
[metadata.resources.limits]
scope = "trial"
max_gpu_memory_gb = 0.0
max_memory_gb = 6.0
max_processes = 512
max_disk_gb = 20.0
disk_paths = ["/app", "/tmp", "/root"]
disk_exclude = []
sustain_sec = 60.0
window_sec = 120.0
trial_max_gpu_memory_gb = 0.0
trial_max_memory_gb = 8.0
measured = "author estimate; no GPU"
[metadata.resources.caps]
main = {{ cpus = 4.0, memory_gb = 8.0, pids = 8192 }}
[agent]
timeout_sec = 7200.0
network_mode = "allowlist"
allowed_hosts = {json.dumps(ALLOWLIST)}
[environment]
build_timeout_sec = 1800.0
cpus = 4
memory_mb = 8192
[verifier]
timeout_sec = {VERIFIER_TIMEOUT_S}.0
environment_mode = "separate"
network_mode = "no-network"
[verifier.environment]
build_timeout_sec = 1800.0
cpus = {VERIFIER_CPUS}
memory_mb = 8192
'''


def instruction(level, name):
    seed = SEEDS[name]
    return f"""# Full-simulator table tennis: develop a program against L{level}

Win one complete match against the frozen sport's scripted L{level} opponent, seed {seed}: the same frozen instance
as `{TWINS[name]}` (its standard-realtime twin; there you see only camera images).
The original Franka Panda, high-level actions, serve laws, limits, scoring and opponent are unchanged.
First to five, win by two from 4:4, cap seven. Full simulator development is allowed; no video is required.

## Development and deliverable
Use `from tools.tt_fullsim.session import Session`; `Session(level={level}, seed={seed})` gives `state()`, `world`,
`spec()`, `act(command)`, `step(n)`, `ready()` and `reset()`. The full simulator (source included) is at `/opt/fullsim`.
Reset rebuilds the WHOLE same-seed match at 0:0. You may inspect/modify private worlds and develop/search with
repeated resets within your agent resource and time limits. These changes never enter the formal match.
Read `/opt/fullsim/README.md` for the complete program API, observation fields, serving phases and game-time units.

Leave `/app/output/policy/program.py` and any helper/data files within that policy directory (512 regular files,
32 MiB total; no links/special files). Define `make_policy(config)` returning an object with `act(view)`.
The object persists for the full match. `view` contains `state`, full declared `truth`, `scores`, `observation`.
Return one original high action, `{{"type":"ready"}}` during a point's review, or `None`. Helpers in the policy
folder are importable. No model/API calls are available during formal evaluation. Submit executable policy code,
not a pre-recorded trajectory or a claimed score. Write a valid program early and update it as you improve.

## Formal evaluation
After development, a separate no-network verifier runs your final program as an unprivileged process against a
fresh unmodified original simulator. Your program may read a public read-only copy of the full simulator
(`/opt/dev`, the same files as `/opt/fullsim`) for its own predictions; it cannot read the trusted simulator, referee
or logs. Formal full-state snapshots are read-only values, not a mutable
world object. Formal reset and score rollback are not allowed. The original realtime clock runs at S=10 even
while your program computes; point reviews freeze the world under the existing rules. One response per observation,
one action at a time. See `config["spec"]` and the README for the policy execution, load, review and call limits.
The match ends as in `{TWINS[name]}`: when it is over, or at that task's cutoff ({WALL_LIMIT_S} s of wall
time), where an unfinished match is not won; a program error does not win either. The platform records the executed
actions and replays that trusted journal in a fresh process. Success requires a completed win,
valid original referee result and matching hashes/scores/steps/outcome. The generated trajectory is evidence,
not your submission. This fixed-instance result does not measure unseen-instance generalization.

## Strategy notes
Your serve begins with `waiting`, then `open`, then `tossed`. Toss only when `open`. There is a stationary
0.1 game-second pause before projection; contact the ball on its fall. Use `spec.serve` and the original action
schema for legality. Every control step is 0.01 game seconds; at S=10 that is 0.1 wall seconds.
"""


def build(out, hub=None):
    for level, name in TASKS:
        seed = SEEDS[name]
        dst = out / name
        if dst.exists():
            shutil.rmtree(dst)
        env, tests, solution = dst / "environment", dst / "tests", dst / "solution"
        env.mkdir(parents=True)
        tests.mkdir()
        solution.mkdir()
        bundle(env / "fullsim", public=True, source=source_for(name))
        bundle(tests / "trusted", public=False, source=source_for(name))
        # Public dev copy must be a different readable tree, not the private trusted tree.
        copy_tree(env / "fullsim", tests / "dev")
        base = (TEMPLATES / "base.Dockerfile").read_text()
        (env / "Dockerfile").write_text(
            base
            + """COPY fullsim/ /opt/fullsim/
COPY fullsim/README.md /opt/fullsim/README.md
ENV PYTHONPATH=/opt/fullsim
WORKDIR /app
RUN mkdir -p /app/output && chmod -R a+rX /opt/fullsim
"""
        )
        for root in (env / "fullsim", tests / "dev"):
            (root / "README.md").write_text(
                (TEMPLATES / "README.md")
                .read_text()
                .replace("@LEVEL@", str(level))
                .replace("@SEED@", str(seed))
                .replace("@TWIN@", TWINS[name])
            )
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
        (tests / INSTANCE_FILE).write_text(
            json.dumps({"level": level, "seed": seed, "slowdown": 10, "wall_limit_s": WALL_LIMIT_S}) + "\n"
        )
        (env / INSTANCE_FILE).write_text((tests / INSTANCE_FILE).read_text())
        (tests / "test.sh").write_text("""#!/bin/bash
set -eu
mkdir -p /logs/verifier
rm -rf /logs/verifier/* /logs/verifier/.[!.]*
chmod 755 /logs/verifier
python /tests/grade.py > /logs/verifier/grade.log 2>&1
""")
        (tests / "test.sh").chmod(0o755)
        # The oracle is deliberately only in solution/, never the agent's development source.
        reference = (Path(__file__).resolve().parent / "oracle/program.py").read_text()
        reference = reference.replace(
            'sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "sports/tabletennis"))', ""
        )
        (solution / "program.py").write_text(reference)
        shutil.copy2(source_for(name) / "sport/builtin_players.py", solution / "builtin_players.py")
        (solution / "solve.sh").write_text("""#!/bin/bash
set -eu
mkdir -p /app/output/policy
cp /solution/program.py /solution/builtin_players.py /app/output/policy/
""")
        (solution / "solve.sh").chmod(0o755)
        (dst / "task.toml").write_text(task_toml(level, name))
        (dst / "instruction.md").write_text(instruction(level, name))
        (dst / "README.md").write_text(f"""# {name}

## Task
{" ".join(instruction(level, name).split("## Development")[0].splitlines()[2:4])}

## Difficulty
Same frozen sport and instance as `{TWINS[name]}`: scripted level {level}, seed {seed}; full-simulator
development and the full state instead of camera images.

## Reference solution
`solution/solve.sh` submits the full-state reference program (the camera-only reference player's serve and stroke
planner fed the true ball state).

## Verification
Separate no-network verifier; root-owned trusted source (unreadable to the program), the program as `nobody` with a
public read-only copy of the full simulator (`/opt/dev`), the original core clock at S = 10, one fresh-process journal
replay (the original service's own) that must agree with the live match, then the replay video (`replay.mp4`, after
the verdict). The match ends as in the twin: over, or unfinished at {WALL_LIMIT_S} s. The verdict of this live,
closed-loop match depends on the verifier host's speed, as for the standard-realtime twin: the verifier's CPUs are
pinned ({VERIFIER_CPUS}, minimum = cap). If any process of the program's user survives the end of the match, the trial
is the program's 0 (never a win, never a retry).
""")
        if hub:
            sys.path.insert(0, str(hub / "scripts"))
            importlib.import_module("task_conventions").normalize(dst)
        else:
            with (dst / "instruction.md").open("a") as f:
                f.write("\n## Time limit\nYou have 7200 seconds to complete this task.\n")
    return [name for _, name in TASKS]


def snapshot(root):
    return {
        str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mode & 0o777)
        for p in sorted(root.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts
    }


def twin_identity(tasks):
    """PROTOCOL H.7: the privileged twin runs its standard-realtime twin's frozen simulator (environment/sim) byte for
    byte (the trusted and the public copies; the public one without the reference player) and the same seed/level."""
    for level, name in TASKS:
        sim = tasks / TWINS[name] / "environment/sim"
        compose = (tasks / TWINS[name] / "environment/docker-compose.yaml").read_text()
        for key, value in (("RO_SEED", SEEDS[name]), ("RO_LEVEL", level), ("RO_FORMAT", "match"), ("RO_SLOWDOWN", 10),
                           ("RCB_ACTION_LEVEL", "high"), ("READY_TIMEOUT_S", 300), ("RCB_WALL_CLOCK_S", WALL_LIMIT_S)):
            if f'{key}: "{value}"' not in compose:
                raise SystemExit(f"{name}: twin {TWINS[name]} does not run {key} = {value}")
        for copy in ("tests/trusted", "tests/dev", "environment/fullsim"):
            root = tasks / name / copy
            for f in sorted(p for p in sim.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
                rel = f.relative_to(sim)
                mine = root / ("sports/tabletennis" / rel.relative_to("sport") if rel.parts[0] == "sport" else rel)
                public = copy != "tests/trusted"
                if (
                    "lowlevel" in rel.parts
                    or public
                    and (mine.name == "builtin_players.py" or any(rel.as_posix().startswith(d) for d in PUBLIC_DROP))
                ):
                    continue
                if not mine.is_file() or mine.read_bytes() != (public_bytes(f) if public else f.read_bytes()):
                    raise SystemExit(f"{name}/{copy}: {mine.relative_to(root)} differs from {TWINS[name]}'s sim/{rel}")


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--out", type=Path)
    p.add_argument("--hub", type=Path, default=ROOT)
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    if not args.out and not args.hub:
        p.error("provide --out or --hub")
    out = args.out or args.hub / "tasks"
    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            for twin in TWINS.values():  # normalize renders the README's Twin row from the sibling directory
                if (out / twin).is_dir():
                    (Path(tmp) / twin).symlink_to(out / twin)
            build(Path(tmp), args.hub)
            for _, name in TASKS:
                if snapshot(Path(tmp) / name) != snapshot(out / name):
                    raise SystemExit(f"generated task differs: {name}")
        if args.hub:
            twin_identity(out)
        print("fullsim policy tasks match exporter; the trusted simulator is byte-identical to each twin's")
    else:
        build(out, args.hub)
        print("wrote " + ", ".join(n for _, n in TASKS))


if __name__ == "__main__":
    main()
