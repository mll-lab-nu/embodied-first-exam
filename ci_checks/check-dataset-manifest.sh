#!/usr/bin/env bash
# Every task dir under tasks/ must be listed in tasks/dataset.toml and vice versa.
root="$(cd "$(dirname "$0")/.." && pwd)"; python3 - "$root" <<'PY'
import sys, tomllib, pathlib
root = pathlib.Path(sys.argv[1]); d = tomllib.load(open(root / "tasks" / "dataset.toml", "rb"))
listed = {t["name"].split("/")[-1] if "/" in t.get("name", "") else pathlib.Path(t.get("path", t.get("name"))).name for t in d.get("tasks", [])}
present = {p.name for p in (root / "tasks").iterdir() if p.is_dir() and (p / "task.toml").exists()}
rc = 0
for x in sorted(present - listed): print(f"FAIL tasks/{x}: not in tasks/dataset.toml"); rc = 1
for x in sorted(listed - present): print(f"FAIL dataset.toml lists missing task {x}"); rc = 1
sys.exit(rc)
PY
