"""No-network, standard-library verifier: accepts only sidecar-collected evidence."""

import hashlib
import json
import math
import os
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def verdict(data, instance_path):
    # standard mode (PROTOCOL §4): the verdict is the sidecar's own evaluation of the sealed policy, transcribed here
    empty = {
        "success": 0,
        "live_success": 0,
        "graded_by_live": 1,
        "replays": 0,
        "infra_error": 1,
        "progress": 0.0,
        "final_reward": 0.0,
        "success_rate": 0.0,
        "episodes": 0,
    }
    try:
        instance_path = Path(instance_path)
        instance = json.loads(instance_path.read_text())
        final = json.loads((Path(data) / "final.json").read_text())
        if (
            final["schema"] != "landing-final/1"
            or final["protocol"] != "eai-policy/1.0"
            or final["finalized"] is not True
            or final["infra_error"] is not False
            or final["instance_sha256"] != hashlib.sha256(instance_path.read_bytes()).hexdigest()
        ):
            return empty
        if final["no_submission"] is True and final["grade_sha256"] is None:
            return {**empty, "infra_error": 0}
        if final["no_submission"] is not False:
            return empty
        report = json.loads((Path(data) / "session/grade.json").read_text())
        if (
            digest(report) != final["grade_sha256"]
            or report["task_version"] != instance["task_version"]
            or report["score_version"] != instance["score_version"]
        ):
            return empty
        rows = report["episodes"]
        count = len(instance["bank"]["held_out"])
        if len(rows) != count or [r["case"] for r in rows] != list(range(count)):
            return empty
        for row in rows:
            if row["replay_verified"] is not True or type(row["success"]) is not bool:
                return empty
            if type(row["score"]) not in (int, float) or not math.isfinite(row["score"]):
                return empty
            if not 0 <= row["score"] <= 100 or (not row["success"] and row["score"] != 0):
                return empty
        successes = sum(r["success"] for r in rows)
        score = sum(r["score"] for r in rows) / count
        if report["score"] != score or report["successes"] != successes or final.get("success") is not (successes == count):
            return empty
        return {
            **empty,
            "success": int(successes == count),
            "live_success": int(successes == count),
            "infra_error": 0,
            "progress": score / 100,
            "final_reward": score,
            "success_rate": successes / count,
            "episodes": count,
        }
    except (OSError, ValueError, TypeError, KeyError, ZeroDivisionError):
        return empty


def main():
    result = verdict(os.environ.get("RCB_DATA", "/data"), "/tests/instance.json")
    log = Path(os.environ.get("RCB_VERIFIER_LOG_DIR", "/logs/verifier"))
    log.mkdir(parents=True, exist_ok=True)
    (log / "reward.txt").write_text(str(result["success"]) + "\n")
    (log / "reward.json").write_text(json.dumps(result, allow_nan=False))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
