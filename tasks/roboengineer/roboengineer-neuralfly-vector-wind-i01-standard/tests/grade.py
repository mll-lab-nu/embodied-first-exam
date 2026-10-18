"""Independent verdict; optional diagnostics are operator-only, never public metrics."""

import hashlib
import json
import locale
import math
import os
from pathlib import Path


def digest(v):
    return hashlib.sha256(json.dumps(v, sort_keys=True, allow_nan=False).encode()).hexdigest()


def verdict(data, instance, diagnostics=None):
    """Return the unchanged score contract, optionally recording private rejection evidence.

    Input hashes identify the exact bytes read, not a later filesystem snapshot.
    Only inputs reached before rejection appear in the diagnostic manifest.
    """
    # standard mode (PROTOCOL §4): the verdict is the sidecar's own evaluation of the selected policy, transcribed here
    empty = {
        "success": 0,
        "infra_error": 1,
        "live_success": 0,
        "graded_by_live": 1,
        "replays": 0,
        "final_reward": 0.0,
        "progress": 0.0,
        "success_rate": 0.0,
        "episodes": 0,
    }
    stage, path = "initialization", None
    if diagnostics is not None:
        diagnostics.clear()
        diagnostics.update(schema="control-transfer-verifier-diagnostics/1", status="checking", inputs=[])

    def read_json(filename):
        nonlocal path
        path = str(filename)
        entry = {"path": path, "stage": stage}
        if diagnostics is not None:
            diagnostics["inputs"].append(entry)
        raw = Path(filename).read_bytes()
        if diagnostics is not None:
            entry.update(size_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        # Match Path.read_text's default encoding, while hashing the exact bytes parsed.
        return json.loads(raw.decode(locale.getpreferredencoding(False)))

    def reject(exc=None):
        if diagnostics is not None:
            diagnostics.update(status="rejected", fail_stage=stage, path=path)
            if exc is not None:
                diagnostics.update(exception_class=type(exc).__name__, errno=getattr(exc, "errno", None))
        return empty

    def accept(result):
        if diagnostics is not None:
            diagnostics.update(status="accepted", fail_stage=None)
        return result

    try:
        stage = "read_instance"
        spec = read_json(instance)
        stage = "read_final"
        f = read_json(Path(data) / "final.json")
        stage = "final_schema"
        if f["schema"] != "control-transfer-final/1":
            return reject()
        stage = "instance_digest"
        expected = digest(spec)
        if diagnostics is not None:
            diagnostics.update(expected_instance_sha256=expected, actual_instance_sha256=f.get("instance_sha256"))
        if f["instance_sha256"] != expected:
            return reject()
        stage = "finalized_flag"
        if f["finalized"] is not True or f.get("graded_by") != "live":
            return reject()
        stage = "infrastructure_flag"
        if f["infra_error"] is not False:
            return reject()
        stage = "evidence_digest"
        rows = f["episodes"]
        expected = digest(rows)
        if diagnostics is not None:
            diagnostics.update(expected_evidence_sha256=expected, actual_evidence_sha256=f.get("evidence_sha256"))
        if expected != f["evidence_sha256"]:
            return reject()
        stage = "submission"
        if f["no_submission"] is True and rows == []:
            return accept({**empty, "infra_error": 0})
        stage = "episode_bank"
        n = len(spec["bank"]["held_out"])
        if f["no_submission"] is not False or len(rows) != n or [r["case"] for r in rows] != list(range(n)):
            return reject()
        for index, r in enumerate(rows):
            stage = "episode_metrics"
            if diagnostics is not None:
                diagnostics["case"] = index
            if (
                type(r["success"]) is not bool
                or r["replay_verified"] is not True
                or type(r["score"]) not in (int, float)
                or not math.isfinite(r["score"])
                or not 0 <= r["score"] <= 100
            ):
                return reject()
            stage = "state_digest"
            if not isinstance(r["state_sha256"], str) or len(r["state_sha256"]) != 64:
                return reject()
        stage = "runtime_requirements"
        requirements = spec.get("evaluation_requirements")
        if requirements:
            for i in range(n):
                for replay in ("a", "b"):
                    if diagnostics is not None:
                        diagnostics.update(case=i, replay=replay)
                    stage = "read_runtime"
                    evidence = read_json(Path(data) / "held-out" / f"case-{i}-{replay}.runtime.json")
                    stage = "runtime_requirements"
                    if any(evidence.get(key) != value for key, value in requirements.items()):
                        return reject()
        stage = "aggregate"
        score = sum(r["score"] for r in rows) / n
        rate = sum(r["success"] for r in rows) / n
        if f.get("success") is not (rate == 1):
            return reject()
        return accept(
            {
                **empty,
                "success": int(rate == 1),
                "infra_error": 0,
                "live_success": int(rate == 1),
                "final_reward": score,
                "progress": score / 100,
                "success_rate": rate,
                "episodes": n,
            }
        )
    except (OSError, KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        return reject(exc)


if __name__ == "__main__":
    diagnostics = {}
    result = verdict(os.environ.get("RCB_DATA", "/data"), "/tests/instance.json", diagnostics)
    out = Path("/logs/verifier")
    out.mkdir(parents=True, exist_ok=True)
    (out / "reward.json").write_text(json.dumps(result))
    (out / "reward.txt").write_text(str(result["success"]) + "\n")
    try:
        (out / "diagnostics.json").write_text(json.dumps(diagnostics, sort_keys=True, allow_nan=False) + "\n")
    except OSError:
        pass  # Diagnostic storage must not change a completed verdict.
    print(json.dumps(result))
