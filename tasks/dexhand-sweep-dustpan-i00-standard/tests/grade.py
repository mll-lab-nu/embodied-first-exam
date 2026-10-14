"""Grade trusted sidecar artifacts; no agent-produced success claim is read."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil


def verdict(data: dict) -> dict:
    no_verdict = not data.get("finalized") or data.get("deterministic") is None
    infra = bool(data.get("infra_error")) or no_verdict
    success = (
        bool(data.get("success"))
        and bool(data.get("replay_success"))
        and bool(data.get("deterministic"))
        and bool(data.get("live_matches_replay"))
        and not infra
    )
    return {
        "success": int(success),
        "live_success": int(bool(data.get("success"))),
        "replay_success": int(bool(data.get("replay_success"))),
        "deterministic": int(bool(data.get("deterministic"))),
        "live_matches_replay": int(bool(data.get("live_matches_replay"))),
        "infra_error": int(infra),
        "sim_error": int(data.get("reason") == "error"),
        "finalized": int(bool(data.get("finalized"))),
        "no_verdict": int(no_verdict),
        "n_actions": int(data.get("n_actions") or 0),
        "sim_steps": int(data.get("control_steps") or data.get("steps") or 0),
        "calls": int(data.get("calls") or 0),
        "sim_startups": int(data.get("sim_startups") or 0),
        "resumes": int(data.get("resumes") or 0),
        "resume_state_mismatch": int(data.get("resume_state_mismatch") or 0),
        "hand_wuji": int(data.get("hand") == "wuji"),
        "resets": int(data.get("resets") or 0),
        "reset_budget": int(data.get("reset_budget") or 0),
    }


def main() -> None:
    directory = Path(os.environ.get("RCB_DATA", "/data"))
    log = Path(os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier"))
    log.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads((directory / "final.json").read_text())
        if not isinstance(data, dict):
            raise ValueError("final.json must be an object")
        result = verdict(data)
    except (OSError, ValueError, TypeError):
        result = {"success": 0, "deterministic": 0, "infra_error": 1, "missing_log": 1}
    for name in ("trajectory.npz", "episode.jsonl", "replay.mp4"):
        if (directory / name).is_file():
            shutil.copyfile(directory / name, log / name)
    (log / "reward.txt").write_text(f"{result['success']}\n")
    (log / "reward.json").write_text(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
