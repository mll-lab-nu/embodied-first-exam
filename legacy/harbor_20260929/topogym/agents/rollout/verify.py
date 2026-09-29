"""Root-only finalization and binary Harbor reward from manager evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

from .client import call
from .protocol import ADMIN_SOCKET, atomic_json


def smoke_motion(root):
    """Read manager tick evidence for the fixed up/down smoke instruction."""
    ends = {}
    with (Path(root) / "private/physics_states.jsonl").open() as stream:
        for line in stream:
            row = json.loads(line)
            if row["segment_id"] in {0, 1, 2}:
                ends[row["segment_id"]] = row["robot"]
    if set(ends) != {0, 1, 2}:
        return {"checked": True, "passed": False, "reason": "missing_tick_evidence"}
    group = next(iter(ends[0]))
    positions = [ends[i][group]["tcp_position_world_m"] for i in range(3)]
    up = positions[1][2] - positions[0][2]
    down = positions[2][2] - positions[1][2]
    return {"checked": True, "passed": up > 1e-6 and down < -1e-6,
            "first_delta_z_m": up, "second_delta_z_m": down}


def score(root):
    root = Path(root)
    final = json.loads((root / "session_final.json").read_text())
    instance = json.loads((root / "instance.json").read_text())
    core = json.loads((root / "report.json").read_text())
    def read_segment(identity):
        path = root / f"segments/segment_{identity}/result.json"
        if not path.exists():  # Read historical archives without rewriting them.
            path = root / f"segments/segment_{identity}.json"
        return json.loads(path.read_text())
    initial = read_segment(0)
    video_history = initial.get("schema_version", 1) >= 2
    segments = []
    for receipt in final["requests"]:
        if receipt["request_status"] == "finished":
            result = read_segment(receipt["segment_id"])
            if result["episode_id"] != final["episode_id"] or result["request_id"] != receipt["request_id"]:
                raise ValueError("Segment identity mismatch")
            segments.append(result)
    sealed = (final["evidence_complete"] and core["status"] == "complete"
              and initial["episode_id"] == final["episode_id"]
              and all(r["request_status"] == "finished" for r in final["requests"])
              and all(s["evidence_complete"] and s["status"] == "complete" for s in segments))
    healthy = sealed and all(s["reason"] in {"policy_done", "env_terminal", "env_time_limit"} for s in segments)
    healthy &= final["stop_reason"] in {None, "agent_finished"}
    if video_history:
        sealed &= all(s["evidence_complete"] and s["status"] == "complete"
            and set(s.get("logs", {})) == {"steps", "events"}
            and s.get("history", {}).get("steps") == s["saved_physics_steps"] + 1 for s in [initial, *segments])
        healthy &= sealed and initial["reason"] in {"initial_observation", "env_terminal", "env_time_limit"}
    previous = initial["end_state_ref"] if video_history else initial["state_ref"]
    previous_rgb = initial["media"].get("final_frame_sha256", {}) if video_history else initial["rgb"]
    for segment in segments:
        healthy &= segment["start_state_ref"] == previous
        previous = segment["end_state_ref"]
        if instance["simulator"].get("enable_rgb", True):
            if video_history:
                current = segment["media"].get("initial_frame_sha256", {})
                healthy &= bool(current) and current == previous_rgb
                previous_rgb = segment["media"].get("final_frame_sha256", {})
            else:
                current = segment["media"].get("initial", {})
                healthy &= bool(current) and all(camera in previous_rgb and
                    entry["sha256"] == previous_rgb[camera]["sha256"] for camera, entry in current.items())
                previous_rgb = segment["media"].get("final", {})
    if video_history and instance["simulator"].get("enable_rgb", True):
        healthy &= all(bool(s["media"].get("videos")) and bool(s["media"].get("frame_map"))
                       and s["media"].get("initial_frame_state_id") == s["start_state_ref"]["state_id"]
                       and s["media"].get("final_frame_state_id") == s["end_state_ref"]["state_id"]
                       for s in [initial, *segments])
    feedback = final["final_feedback"]
    evaluation = feedback.get("evaluation_status", "unavailable")
    success = feedback.get("task_success") if evaluation == "available" else None
    mode = instance.get("evaluation", "task_success")
    motion = {"checked": False, "passed": None}
    if mode == "pipeline_smoke":
        pipeline = bool(healthy and len(segments) >= 2 and all(s["control_steps"] > 0 for s in segments))
        if instance["simulator"].get("enable_rgb", True):
            pipeline &= bool(initial["media"].get("videos") if video_history else initial["rgb"])
            pipeline &= all(bool(s["media"]["videos"]) for s in segments)
        if instance["simulator"].get("control_mode") == "EE_DELTA":
            motion = smoke_motion(root)
            pipeline &= motion["passed"]
        reward = int(pipeline)
    elif mode == "task_success":
        pipeline = bool(healthy and (segments or (video_history and initial["reason"] == "env_terminal")))
        reward = int(pipeline and success is True)
    else:
        raise ValueError("Unknown evaluation mode")
    usage = final["usage"]
    if (root / "usage_final.json").exists():
        usage = json.loads((root / "usage_final.json").read_text())
    enforced = usage["mode"] != "off"
    budget_ok = None if not enforced else bool(usage.get("closed") and usage.get("budget_qualified")
        and usage.get("usage_complete") and not usage.get("stop") and not usage.get("failure_reason"))
    failure = usage.get("failure_reason") if enforced else None
    if enforced and not budget_ok:
        reward, pipeline = 0, False
        failure = failure or "usage_incomplete"
    return dict(schema_version=2, evaluation=mode, reward=reward,
        pipeline_passed=bool(pipeline), task_success=success, evaluation_status=evaluation,
        scoring_eligible=bool(mode == "task_success" and healthy and evaluation == "available"),
        evidence_complete=bool(sealed), segments=len(segments), stop_reason=final["stop_reason"],
        smoke_motion=motion,
        token_budget_enforced=enforced, budget_qualified=budget_ok, failure_reason=failure,
        outcome="succeeded" if reward else "failed", usage=usage)


def seal_archive(root):
    root = Path(root)
    entries = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Archive contains symlink")
        if path.is_file() and path.name != "archive_manifest.json":
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            entries[str(path.relative_to(root))] = dict(sha256=digest.hexdigest(), size_bytes=path.stat().st_size)
    atomic_json(root / "archive_manifest.json", dict(schema_version=1, files=entries), 0o600)


def finalize(root, *, admin_socket=ADMIN_SOCKET, timeout=45):
    root = Path(root)
    if not (root / "session_final.json").exists():
        call({"operation": "finish"}, admin_socket)
    end = time.monotonic() + timeout
    while not (root / "session_final.json").exists():
        if time.monotonic() >= end:
            raise TimeoutError("Worker did not finalize; evidence remains incomplete")
        time.sleep(.2)
    # Verify the publication descriptors before producing a trusted success score.
    from topogym.utils.io import relative_file, sha256_file
    for entry in json.loads((root / "publication.json").read_text())["artifacts"].values():
        path = relative_file(root, entry["archive_relative"])
        if path.stat().st_size != entry["size_bytes"] or sha256_file(path) != entry["sha256"]:
            raise ValueError("Published artifact integrity failure")
    result = score(root)
    atomic_json(root / "verification.json", result, 0o600)
    seal_archive(root)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/trial/rollout"))
    parser.add_argument("--reward-dir", type=Path, default=Path("/logs/verifier"))
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Verification requires the manager identity")
    args.reward_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = finalize(args.root)
    except Exception as error:
        result = dict(reward=0, pipeline_passed=False, task_success=None,
                      evidence_complete=False, error=type(error).__name__)
        atomic_json(args.reward_dir / "verification.json", result)
        (args.reward_dir / "reward.txt").write_text("0\n")
        raise
    atomic_json(args.reward_dir / "verification.json", result)
    (args.reward_dir / "reward.txt").write_text(str(result["reward"]) + "\n")


if __name__ == "__main__":
    main()
