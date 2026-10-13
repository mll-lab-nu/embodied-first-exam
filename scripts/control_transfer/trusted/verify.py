"""Independent, offline verdict from simulator-owned evidence only."""

import hashlib, json, math, os
from pathlib import Path


def digest(v):
    return hashlib.sha256(json.dumps(v, sort_keys=True, allow_nan=False).encode()).hexdigest()


def verdict(data, instance):
    empty = {
        "success": 0,
        "infra_error": 1,
        "deterministic": 0,
        "final_reward": 0.0,
        "progress": 0.0,
        "success_rate": 0.0,
        "episodes": 0,
    }
    try:
        spec = json.loads(Path(instance).read_text())
        f = json.loads((Path(data) / "final.json").read_text())
        if (
            f["schema"] != "control-transfer-final/1"
            or f["instance_sha256"] != digest(spec)
            or f["finalized"] is not True
            or f["infra_error"] is not False
        ):
            return empty
        rows = f["episodes"]
        if digest(rows) != f["evidence_sha256"]:
            return empty
        if f["no_submission"] is True and rows == []:
            return {**empty, "infra_error": 0}
        n = len(spec["bank"]["held_out"])
        if f["no_submission"] is not False or len(rows) != n or [r["case"] for r in rows] != list(range(n)):
            return empty
        for r in rows:
            if (
                type(r["success"]) is not bool
                or r["replay_verified"] is not True
                or type(r["score"]) not in (int, float)
                or not math.isfinite(r["score"])
                or not 0 <= r["score"] <= 100
            ):
                return empty
            if not isinstance(r["state_sha256"], str) or len(r["state_sha256"]) != 64:
                return empty
        score = sum(r["score"] for r in rows) / n
        rate = sum(r["success"] for r in rows) / n
        return {
            **empty,
            "success": int(rate == 1),
            "infra_error": 0,
            "deterministic": 1,
            "final_reward": score,
            "progress": score / 100,
            "success_rate": rate,
            "episodes": n,
        }
    except (OSError, KeyError, TypeError, ValueError, ZeroDivisionError):
        return empty


if __name__ == "__main__":
    result = verdict(os.environ.get("RCB_DATA", "/data"), "/tests/instance.json")
    out = Path("/logs/verifier")
    out.mkdir(parents=True, exist_ok=True)
    (out / "reward.json").write_text(json.dumps(result))
    (out / "reward.txt").write_text(str(result["success"]) + "\n")
    print(json.dumps(result))
