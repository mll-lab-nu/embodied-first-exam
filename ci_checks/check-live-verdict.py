#!/usr/bin/env python3
"""The standard modes are graded by the live episode (docs/PROTOCOL.md H.4; owner, 2026-10-17, board 0151): the sim
sidecar judges the episode it ran and the verifier transcribes its `final.json`; no replay grades it. Advisory: the
invariant itself (the verdict from a trusted source) is held by check-verifier-isolation.sh; this check reports a
standard task whose grader still follows the replay rule, and a grader that breaks the infrastructure rule of
RUNNING.md ("Infrastructure failures"). For every standard / standard-realtime task:
  - static: its verifier code (tests/*.py) reports `graded_by_live` and reads no `replay_success` (a verdict that waits
    for a replay, or a replay that can decide);
  - run: each distinct tests/grade.py (one run per content, standard library only) is given synthetic records in a
    temporary directory (RCB_DATA, RCB_VERIFIER_LOG_DIR) and must answer
      no final.json                                             -> reward 0, infra_error 1 (no verdict on the agent)
      a finalized live failure at the cutoff                    -> reward 0, infra_error 0 (the agent's result)
      a give-up after crashes inside the agent's calls          -> reward 0, infra_error 0 (never a free retry)
      replay_success / deterministic true, the live episode not -> reward 0 (a replay never grants a success)
    A grader that does not read RCB_DATA / RCB_VERIFIER_LOG_DIR is checked statically only.
Tasks a benchmark exports with its own runtime (`scripts/<bench>/exported.toml`) are checked the same way.

    python3 ci_checks/check-live-verdict.py [task dirs]      # default: every task
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = (
    ("no final.json", None, 0, 1),
    ("a finalized live failure at the cutoff",
     {"finalized": True, "graded_by": "live", "replays": 0, "success": False, "live_success": False, "done": True,
      "reason": "timeout", "n_actions": 10, "video": True}, 0, 0),
    ("a give-up after crashes inside the agent's calls",
     {"finalized": True, "graded_by": "live", "replays": 0, "success": False, "live_success": False, "done": True,
      "reason": "sim_crashed_on_call", "gave_up": True}, 0, 0),
    ("a replay success where the live episode failed",
     {"finalized": True, "success": False, "live_success": False, "replay_success": True, "deterministic": True,
      "done": True, "reason": "timeout", "n_actions": 10}, 0, None),
)


def mode_of(task: Path) -> str:
    for m in ("standard-realtime", "standard"):
        if task.name.endswith("-" + m):
            return m
    return ""


def run_grader(grader: Path, record: dict | None) -> tuple[int | None, dict, str]:
    with tempfile.TemporaryDirectory(prefix="rcb-live-") as tmp:
        data, log = Path(tmp, "data"), Path(tmp, "log")
        data.mkdir()
        log.mkdir()
        if record is not None:
            (data / "final.json").write_text(json.dumps(record))
        env = {**os.environ, "RCB_DATA": str(data), "RCB_VERIFIER_LOG_DIR": str(log), "PYTHONDONTWRITEBYTECODE": "1"}
        try:
            p = subprocess.run([sys.executable, str(grader.resolve())], cwd=tmp, env=env, capture_output=True, text=True,
                               timeout=60)
        except subprocess.TimeoutExpired:
            return None, {}, "timed out after 60 s"
        try:
            txt = (log / "reward.txt").read_text().split()
            reward = int(float(txt[0])) if txt else None
        except (OSError, ValueError):
            reward = None
        try:
            rw = json.loads((log / "reward.json").read_text())
        except (OSError, ValueError):
            rw = {}
        return reward, rw if isinstance(rw, dict) else {}, (p.stderr or p.stdout)[-300:]


def check(tasks: list[Path]) -> list[str]:
    errs: list[str] = []
    seen: dict[str, str] = {}                       # grader content hash -> the first task that has it
    for task in tasks:
        if not mode_of(task):
            continue
        src = "\n".join(p.read_text(errors="replace") for p in sorted((task / "tests").glob("*.py")) if p.is_file())
        if not src:
            continue
        if "graded_by_live" not in src:
            errs.append(f"{task.name}: its verifier reports no `graded_by_live` (the standard modes are graded by the "
                        "live episode, PROTOCOL H.4)")
        if re.search(r"""["']replay_success["']""", src):
            errs.append(f"{task.name}: its verifier reads `replay_success` (no replay grades a standard episode)")
        grader = task / "tests" / "grade.py"
        if not grader.is_file():
            continue
        text = grader.read_text(errors="replace")
        if "RCB_DATA" not in text or "RCB_VERIFIER_LOG_DIR" not in text:
            continue
        h = hashlib.sha256(text.encode()).hexdigest()
        if h in seen:
            continue
        seen[h] = task.name
        for name, record, want_reward, want_infra in CASES:
            reward, rw, tail = run_grader(grader, record)
            if reward is None:
                errs.append(f"{task.name}: tests/grade.py on {name}: no reward.txt ({tail.strip()[-160:]})")
                continue
            if reward != want_reward:
                errs.append(f"{task.name}: tests/grade.py on {name}: reward {reward}, expected {want_reward}")
            if want_infra is not None and int(bool(rw.get("infra_error"))) != want_infra:
                errs.append(f"{task.name}: tests/grade.py on {name}: infra_error {rw.get('infra_error')}, expected "
                            f"{want_infra}")
    return errs


def main(argv: list[str]) -> int:
    dirs = [Path(a) for a in argv] or sorted(p for p in (ROOT / "tasks").iterdir() if (p / "task.toml").is_file())
    errs = check(dirs)
    n = sum(1 for d in dirs if mode_of(d))
    if errs:
        print(f"FAIL live verdict (PROTOCOL H.4, RUNNING.md \"Infrastructure failures\"; {len(errs)} finding(s)):")
        for e in errs[:60]:
            print("  -", e)
        if len(errs) > 60:
            print(f"  ... {len(errs) - 60} more")
        return 1
    print(f"check-live-verdict: {n} standard task(s) graded by the live episode")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
