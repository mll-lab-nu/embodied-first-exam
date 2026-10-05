"""Audit native Harbor artifacts against the GPU graders' actual score contract."""
from pathlib import Path

from .contracts import BridgeError, digest, read_json
from topogym.simulator.frozen_binding import binding_id


INFRA_FIELDS = ("infra_error", "grader_error", "gpu_lost", "instance_mismatch", "simulator_instability")


def assess_smoke_trial(job, task, mode, lock, *, steps, returncode=0):
    """A scored, bounded real oracle prefix; never a full-solution qualification."""
    result = assess_trial(job, task, mode, lock, returncode=returncode)
    if result["status"] not in {"passed", "score_failed"}:
        return result
    try:
        reward = result["rewards"]
        count = reward.get("n_actions", 0)
        if not isinstance(count, int) or count < 1 or not result.get("trajectory"):
            raise BridgeError("Smoke requires real recorded oracle actions and independent replay")
        if reward.get("video_rendered") != 1:
            raise BridgeError("Smoke requires the native grader's video evidence")
        if mode == "privileged":
            report = read_json(Path(result["trial"]) / "artifacts/app/output/bridge_report.json")
            if report.get("status") not in {"connectivity_smoke_complete", "native_success_pending_harbor_verifier"}:
                raise BridgeError("Oracle callback failed before its smoke boundary")
            if report.get("smoke_steps") != steps or not 1 <= count <= steps:
                raise BridgeError("Oracle prefix length differs from its declared smoke budget")
            if report.get("evaluation", {}).get("action_transfer", {}).get("committed_rows") != count:
                raise BridgeError("Callback evidence differs from the independently replayed prefix")
        elif reward.get("live_rows", 0) < 1:
            raise BridgeError("Standard smoke did not record service-executed actions")
        result.update(status="smoke_passed", connectivity_passed=True, harbor_qualified=False,
                      scope="bounded oracle prefix and native grading, not full solvability")
    except (OSError, ValueError, KeyError, TypeError) as error:
        result.update(status="evidence_failed", connectivity_passed=False)
        result["errors"].append(str(error))
    return result


def assess_trial(job, task, mode, lock, *, agent="oracle", returncode=0):
    """Fail closed on incomplete evidence; determinism/media remain diagnostics.

    Evidence comes from Harbor's isolated verifier, never bridge_report.json.
    A score of zero and an infrastructure failure are separate outcomes.
    """
    result = dict(status="evidence_failed", grade=None, grade_one=False, errors=[])
    try:
        if returncode:
            raise BridgeError(f"Harbor exited {returncode}")
        trials = list(Path(job).glob("*/result.json"))
        if len(trials) != 1:
            raise BridgeError(f"Expected one Harbor trial, found {len(trials)}")
        trial = trials[0].parent
        result.update(trial=str(trial), result=str(trials[0]))
        native = read_json(trials[0])
        if native.get("exception_info") or not native.get("finished_at"):
            result["status"] = "infra_failed"
            raise BridgeError(f"Harbor trial did not finish cleanly: {native.get('exception_info')}")
        if Path(native.get("task_name", "")).name != Path(task).name:
            raise BridgeError("Trial belongs to a different task")
        verifier = trial / "verifier"
        reward = read_json(verifier / "reward.json")
        result.update(rewards=reward, grade=reward.get("success"))
        if reward != (native.get("verifier_result") or {}).get("rewards"):
            raise BridgeError("Harbor rewards disagree with verifier/reward.json")
        if reward.get("success") not in (0, 1) or read_json(verifier / "reward.txt") != reward["success"]:
            raise BridgeError("Missing or inconsistent numeric grade")
        if any(reward.get(key) for key in INFRA_FIELDS):
            result["status"] = "infra_failed"
            raise BridgeError("Verifier infrastructure failure: " + ", ".join(k for k in INFRA_FIELDS if reward.get(k)))
        wanted = binding_id(lock)

        def bound(record):
            if (record.get("instance_exact") is not True
                    or (record.get("runtime_binding") or {}).get("binding_id") != wanted):
                raise BridgeError("Verifier evidence does not match the exact frozen runtime")

        if mode == "standard":
            if reward.get("runtime_binding_ok") != 1 or reward.get("finalized") != 1:
                raise BridgeError("Standard service lacks bound finalization")
            startup = read_json(verifier / "startup_binding.json")
            replay = read_json(verifier / "replay.verdict.json")
            final = read_json(verifier / "final.json")
            bound(startup)
            bound(replay)
            rows = replay.get("replays", [])
            if len(rows) != 1 or not isinstance(rows[0].get("success"), bool):
                raise BridgeError("Missing fresh-process replay verdict")
            if not (verifier / "trajectory.npz").is_file():
                raise BridgeError("Missing service-recorded execution history")
            if (not final.get("finalized") or final.get("gave_up")
                    or any(final.get(k) for k in INFRA_FIELDS)
                    or rows[0].get("episode_end") == "simulator_instability"):
                raise BridgeError("Service finalization/replay failed")
            live, replay_ok = final.get("success"), rows[0]["success"]
            if (not isinstance(live, bool) or final.get("replay_success") != replay_ok
                    or reward.get("live_success") != int(live)
                    or reward.get("replay_success") != int(replay_ok)
                    or reward["success"] != int(live and replay_ok and not reward.get("success_pending_review", 0))):
                # tooling v16 (oraclefix 12): a success with a deep task contact is held for review, not credited
                raise BridgeError("Live/replay evidence disagrees with the grade")
            result.update(live_success=live, replay_success=[replay_ok],
                          trajectory=str(verifier / "trajectory.npz"))
        elif mode == "privileged":
            if reward["success"] == 1 or "replays" in reward:
                if any(reward.get(k) != 1 for k in ("runtime_binding_ok", "instance_exact", "instance_ok")):
                    raise BridgeError("Privileged verdict lacks exact bound replay checks")
                verdict = read_json(verifier / "verdict.json")
                evidence = verdict.get("evidence", {})
                if verdict.get("reward") != reward or verdict.get("success") is not bool(reward["success"]):
                    raise BridgeError("Committed verifier verdict disagrees with the grade")
                if (evidence.get("runtime_binding") or {}).get("binding_id") != wanted:
                    raise BridgeError("Privileged verifier runtime differs from the selected task")
                rows = evidence.get("replays", [])
                if len(rows) < 2 or reward.get("replays") != len(rows):
                    raise BridgeError("Privileged grading requires at least two recorded replays")
                if any(not isinstance(row.get("success"), bool) or row.get("episode_end") == "simulator_instability" for row in rows):
                    raise BridgeError("Replay verdict is missing or numerically unstable")
                successes = [row["success"] for row in rows]
                # tooling v16 (oraclefix 12): tolerant replays only confirm, so a privileged success also needs one replay
                # that met the strict goal within the rows (strict_goal_reached), and a deep task contact holds it for
                # review (success_pending_review). Without this, a grade 0 with all replays successful only in the hold
                # was reported as an evidence failure and stopped the queue.
                expected = all(successes)
                if "strict_goal_reached" in reward:
                    expected = (expected and not reward.get("success_pending_review", 0)
                                and (bool(reward["strict_goal_reached"]) or not reward.get("strict_replay_required", 1)))
                if reward.get("all_success") != int(all(successes)) or reward["success"] != int(expected):
                    raise BridgeError("Independent replay successes disagree with the grade")
                trajectory = trial / "artifacts/app/output/trajectory.npz"
                if evidence.get("trajectory_sha256") != digest(trajectory):
                    raise BridgeError("Verifier replayed a different trajectory")
                if evidence.get("instance_sha256") != digest(Path(task) / "tests/instance.json"):
                    raise BridgeError("Verifier used a different frozen instance")
                result.update(replay_success=successes, trajectory=str(trajectory))
        else:
            raise BridgeError(f"Unknown mode: {mode}")
        expected = 1 if agent == "oracle" else 0
        result.update(status="passed" if reward["success"] == expected else "score_failed",
                      grade_one=agent == "oracle" and reward["success"] == 1,
                      deterministic=reward.get("deterministic"), video_rendered=reward.get("video_rendered"))
    except (BridgeError, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        result["errors"].append(str(error))
        if returncode:
            result["status"] = "infra_failed"
    return result
