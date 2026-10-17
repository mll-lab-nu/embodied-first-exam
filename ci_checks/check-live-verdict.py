#!/usr/bin/env python3
"""The standard modes are graded by the live episode (docs/PROTOCOL.md H.4; owner, 2026-10-17, board 0151): the sim
sidecar judges the episode it ran and the verifier transcribes its `final.json`; no replay grades it. Advisory: the
invariant itself (the verdict from a trusted source) is held by check-verifier-isolation.sh; this check reports a
standard task whose grader still follows the replay rule, and a grader that breaks the infrastructure rule of
RUNNING.md ("Infrastructure failures"). For every standard / standard-realtime task:
  - static: its verifier code (tests/*.py) reports `graded_by_live`; task.toml has a `[[verifier.collect]]` hook on `main` (the agent's
    container: `kill -9 -1`, stopping what the agent left running) before the first hook on the sim sidecar, so
    nothing the agent left running moves the robot before the service is signalled (H.4);
  - run: each distinct tests/grade.py (one run per content, standard library only) is given synthetic records in a
    temporary directory (RCB_DATA, RCB_VERIFIER_LOG_DIR) and must answer
      a finalized live success, no replay fields                -> reward 1, infra_error 0 (no replay is waited for)
      no final.json                                             -> reward 0, infra_error 1 (no verdict on the agent)
      an unfinalized final.json (the hook was killed)           -> reward 0, infra_error 1
      a give-up after crashes between calls (sim_crashed)       -> reward 0, infra_error 1
      a finalized live failure at the cutoff                    -> reward 0, infra_error 0 (the agent's result)
      a give-up after crashes inside the agent's calls          -> reward 0, infra_error 0 (never a free retry)
      an unreadable final.json; a scene off the frozen instance -> reward 0, infra_error 1
      a live success whose settle / hold check failed           -> reward 0, infra_error 0 (`success` decides)
      standard-realtime: a simulator error after the agent's first command -> reward 0, infra_error 0; before it (the
      service records infra_error = 1) -> infra_error 1
      replay_success / deterministic true, the live episode not -> reward 0 (a replay never grants a success)
    The records are the shared layers' common fields; a benchmark whose grader needs more of its own (e.g. a verdict
    file next to final.json) may fail the success case, which is then a finding to read, not a rule. A grader that does
    not read RCB_DATA / RCB_VERIFIER_LOG_DIR, or a task without tests/grade.py, is checked statically only (the summary
    says how many). One run per distinct content of tests/*.py + tests/*.json.

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
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC_ONLY: list[str] = []                         # standard tasks whose grader could not be run here
LIVE_OK = {"finalized": True, "graded_by": "live", "replays": 0, "success": True, "live_success": True, "done": True,
           "reason": "success", "n_actions": 10, "control_steps": 10, "video": True}
CASES = (
    ("a finalized live success", LIVE_OK, 1, 0),
    ("no final.json", None, 0, 1),
    ("an unfinalized final.json", {**LIVE_OK, "finalized": False}, 0, 1),
    ("an unreadable final.json", "{", 0, 1),
    ("a scene off the frozen instance",
     {"finalized": True, "success": False, "live_success": False, "done": True, "reason": "instance_mismatch: start",
      "gave_up": True, "infra_error": 1, "graded_by": "live", "replays": 0}, 0, 1),
    ("a live success whose settle / hold check failed", {**LIVE_OK, "success": False, "live_rule": False}, 0, 0),
    ("a give-up after crashes between calls",
     {"finalized": True, "success": False, "live_success": False, "done": True, "reason": "sim_crashed",
      "gave_up": True, "infra_error": 1}, 0, 1),
    ("a finalized live failure at the cutoff",
     {"finalized": True, "graded_by": "live", "replays": 0, "success": False, "live_success": False, "done": True,
      "reason": "timeout", "n_actions": 10, "video": True}, 0, 0),
    ("a give-up after crashes inside the agent's calls",
     {"finalized": True, "success": False, "live_success": False, "done": True,
      "reason": "sim_crashed_on_call", "gave_up": True}, 0, 0),
    ("a replay success where the live episode failed",
     {"finalized": True, "success": False, "live_success": False, "replay_success": True, "deterministic": True,
      "done": True, "reason": "timeout", "n_actions": 10}, 0, None),
)


# standard-realtime only (STANDARD_MODE Part 3, 2026-10-17): a simulator error after the agent's first command is the
# agent's result; one before it is infrastructure (the service records it so)
RT_CASES = (
    ("standard-realtime: a simulator error after the first command",
     {"finalized": True, "graded_by": "live", "replays": 0, "success": False, "live_success": False, "done": True,
      "reason": "error", "sim_error": 1, "n_actions": 10}, 0, 0),
    ("standard-realtime: a simulator error before the first command",
     {"finalized": True, "graded_by": "live", "replays": 0, "success": False, "live_success": False, "done": True,
      "reason": "error", "sim_error": 1, "infra_error": 1, "n_actions": 0}, 0, 1),
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
            (data / "final.json").write_text(record if isinstance(record, str) else json.dumps(record))
            (data / "trajectory.npz").write_bytes(b"")      # present, as the service always writes one
        env = {**os.environ, "RCB_DATA": str(data), "RCB_VERIFIER_LOG_DIR": str(log), "PYTHONDONTWRITEBYTECODE": "1"}
        try:
            p = subprocess.run([sys.executable, str(grader.resolve())], cwd=tmp, env=env, capture_output=True, text=True,
                               timeout=60)
        except subprocess.TimeoutExpired:
            return None, {}, "timed out after 60 s"
        try:
            txt = (log / "reward.txt").read_text().split()
            reward = int(float(txt[0]) >= 1) if txt else None
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
    STATIC_ONLY.clear()
    for task in tasks:
        if not mode_of(task):
            continue
        src = "\n".join(p.read_text(errors="replace") for p in sorted((task / "tests").glob("*.py")) if p.is_file())
        if not src:
            continue
        if "graded_by_live" not in src:
            errs.append(f"{task.name}: its verifier reports no `graded_by_live` (the standard modes are graded by the "
                        "live episode, PROTOCOL H.4)")
        try:
            hooks = (tomllib.loads((task / "task.toml").read_text()).get("verifier") or {}).get("collect") or []
        except (OSError, tomllib.TOMLDecodeError):
            hooks = []
        svc = [h.get("service") for h in hooks if isinstance(h, dict)]
        first_sim = next((i for i, x in enumerate(svc) if x not in ("main", "rcb_monitor")), None)
        kill = next((i for i, h in enumerate(hooks) if isinstance(h, dict) and h.get("service") == "main"
                     and re.search(r"\bkill\s+-(9|KILL)\s+-1\b", str(h.get("command") or ""))), None)
        if first_sim is not None and (kill is None or kill > first_sim):
            errs.append(f"{task.name}: no collect hook stops the agent's processes (`main`: kill -9 -1) before the sim "
                        "sidecar is signalled (PROTOCOL H.4)")
        grader = task / "tests" / "grade.py"
        if not grader.is_file():
            STATIC_ONLY.append(task.name)
            continue
        text = grader.read_text(errors="replace")
        alltext = "\n".join(p.read_text(errors="replace") for p in (task / "tests").glob("*.py") if p.is_file())
        if "RCB_DATA" not in alltext or "RCB_VERIFIER_LOG_DIR" not in alltext:   # a grader may read them in a module
            STATIC_ONLY.append(task.name)
            continue
        h = hashlib.sha256(b"".join(p.name.encode() + p.read_bytes() for p in sorted((task / "tests").iterdir())
                                    if p.is_file() and p.suffix in (".py", ".json"))).hexdigest()
        if h in seen:
            continue
        seen[h] = task.name
        for name, record, want_reward, want_infra in CASES + (RT_CASES if mode_of(task) == "standard-realtime" else ()):
            reward, rw, tail = run_grader(grader, record)
            if reward is None:
                errs.append(f"{task.name}: tests/grade.py on {name}: no reward.txt ({tail.strip()[-160:]})")
                continue
            if reward != want_reward:
                errs.append(f"{task.name}: tests/grade.py on {name}: reward {reward}, expected {want_reward}")
            try:
                got_infra = int(float(rw.get("infra_error") or 0) != 0)
            except (TypeError, ValueError):
                got_infra = 1
            if want_infra is not None and got_infra != want_infra:
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
    print(f"check-live-verdict: {n} standard task(s) graded by the live episode ({len(STATIC_ONLY)} checked statically "
          "only: no runnable tests/grade.py)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
