"""Separate verifier: require complete trusted evidence and emit numeric rewards."""
import hashlib
import json
from pathlib import Path
import shutil
from .evidence import digest, equivalent_states, load_trajectory, rounded_state, write_json


def grade(instance, evidence, logs):
    evidence,logs = Path(evidence),Path(logs)
    logs.mkdir(parents=True,exist_ok=True)
    # Harbor exposes this directory to main too. Remove planted files/symlinks.
    for child in logs.iterdir():
        if child.name == "test-stdout.txt":
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    metrics = dict(success=0, deterministic=0, replay_consistent=0, n_actions=0, sim_steps=0, final_reward=0,
                   missing_trajectory=0, missing_log=0, grader_error=0, video_rendered=0)
    try:
        if not (evidence/"trajectory.npz").is_file():
            metrics["missing_trajectory"] = 1
        if not (evidence/"final.json").is_file():
            metrics["missing_log"] = 1
        if metrics["missing_trajectory"] or metrics["missing_log"]:
            return metrics
        config = json.loads(Path(instance).read_text())
        final = json.loads((evidence/"final.json").read_text())
        actions,steps,identity,initial = load_trajectory(evidence/"trajectory.npz")
        if final.get("finalized") is not True or final.get("grader_error") != 0:
            raise ValueError("Finalization failed or incomplete")
        if identity != digest(config) or final["instance_sha256"] != identity or final["trajectory_sha256"] != hashlib.sha256((evidence/"trajectory.npz").read_bytes()).hexdigest():
            raise ValueError("Frozen input/evidence identity mismatch")
        replays = final["replays"]
        if len(replays) != 2:
            raise ValueError("Two fresh replay results required")
        measured_states=[]
        for i,result in enumerate(replays,1):
            actual = json.loads((evidence/f"replay-{i}"/"result.json").read_text())
            if result != actual or result["instance_sha256"] != identity or result["initial_sha256"] != initial or result["n_actions"] != len(actions) or result["sim_steps"] != int(steps.sum()):
                raise ValueError("Incomplete or inconsistent replay evidence")
            state=json.loads((evidence/f"replay-{i}"/"final-state.json").read_text())
            measured_states.append(state)
            if digest(state)!=result["final_raw_sha256"] or digest(rounded_state(state))!=result["final_sha256"]:
                raise ValueError("Replay state fingerprint differs from the saved measurements")
        live = final.get("live")
        if config.get("mode") == "limited":
            if not isinstance(live,dict) or live != json.loads((evidence/"live.json").read_text()):
                raise ValueError("Limited mode requires the live service verdict")
            state=json.loads((evidence/"live/final-state.json").read_text())
            measured_states.append(state)
            if digest(state)!=live["final_raw_sha256"] or digest(rounded_state(state))!=live["final_sha256"]:
                raise ValueError("Live state fingerprint differs from saved measurements")
        states = replays + ([live] if live is not None else [])
        deterministic = len({r["final_sha256"] for r in states}) == 1 and all(r["initial_sha256"] == initial for r in states)
        consistent=all(equivalent_states(measured_states[0],s) for s in measured_states[1:])
        success = consistent and all(r["success"] is True and r["scoring_eligible"] is True and r.get("reason") != "error" for r in states)
        if final.get("comparison")!={"algorithm":"si-numeric-v1","atol":1e-9,"rtol":1e-9}:
            raise ValueError("Unsupported replay comparison contract")
        if final["deterministic"] is not deterministic or final["success"] is not success or final.get("replay_consistent") is not consistent:
            raise ValueError("Final verdict disagrees with its evidence")
        metrics.update(success=int(success),deterministic=int(deterministic),replay_consistent=int(consistent),n_actions=len(actions),sim_steps=int(steps.sum()),final_reward=int(success))
        videos = sorted((evidence/"replay-1").glob("recording-*/videos/*.mp4"))
        for video in videos:
            shutil.copyfile(video,logs/f"replay-{video.name}")
        metrics["video_rendered"] = int(bool(videos))
        shutil.copyfile(evidence/"final.json", logs/"final.json")
    except Exception as error:
        metrics["success"] = metrics["final_reward"] = 0
        metrics["grader_error"] = 1
        write_json(logs/"error.json", dict(error=f"{type(error).__name__}: {error}"))
    finally:
        write_json(logs/"reward.json",metrics)
        (logs/"reward.txt").write_text(str(metrics["success"])+"\n")
    return metrics
