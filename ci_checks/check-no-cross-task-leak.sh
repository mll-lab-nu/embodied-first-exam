#!/usr/bin/env bash
# The files a task ships into its container (environment/, tests/) must not mention any OTHER task's
# family. An agent solving one task has no business being handed a curated list of the others -- and the
# capability-class grouping in particular is our own design, not something upstream exposes.
#
# Only identifier-shaped matches count ("walk", 'walk', h1-walk-v0, --task walk). Most family names are
# ordinary English words: "the episode reaches the bar" must not be flagged as leaking `reach`.
t="$1"; python3 - "$t" <<'PY'
import pathlib, re, sys

KEY = lambda text, k: (re.search(rf'^{k} *= *"([^"]*)"', text, re.M) or [None, None])[1]

task_dir = pathlib.Path(sys.argv[1])
sim = KEY((task_dir / "task.toml").read_text(), "simulator")
if not (task_dir.resolve().parent.parent / "scripts" / str(sim) / "gen_tasks.py").is_file():
    sys.exit(0)   # hand-maintained tasks share tooling that may name a default task; generated ones must not
families = {toml.parent.name: KEY(toml.read_text(), "family")
            for toml in task_dir.parent.glob("*/task.toml")}
own = families.get(task_dir.name)
others = {f for f in families.values() if f and f != own}

rc = 0
for sub in ("environment", "tests"):
    for f in sorted((task_dir / sub).rglob("*")):
        if not f.is_file() or f.suffix in (".npz", ".npy", ".pyc"):
            continue
        text = f.read_text(errors="ignore")
        for other in sorted(others):
            o = re.escape(other)
            if re.search(rf"""["']{o}["']|\b\w+-{o}-v\d|--(?:task|family)\s+{o}\b""", text):
                print(f"FAIL {task_dir}: {f.relative_to(task_dir)} names another task ({other})")
                rc = 1
sys.exit(rc)
PY
