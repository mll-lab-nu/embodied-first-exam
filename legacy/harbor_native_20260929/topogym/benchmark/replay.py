"""Fresh-process replay; never run agent code or deserialize Python objects."""
import json
from pathlib import Path
import subprocess
import sys

from .evidence import digest, equivalent_states, load_trajectory, write_json


def replay(instance, trajectory, output, *, record=True):
    from .session import Session
    actions, counts, identity, initial = load_trajectory(trajectory)
    config = json.loads(Path(instance).read_text())
    if digest(config) != identity:
        raise ValueError("Trajectory belongs to a different frozen instance")
    with Session(config, output=output, record=record) as session:
        if session.initial != initial:
            raise ValueError("Initial-state fingerprint differs")
        if actions.shape[1] != session.robot.action_dim:
            raise ValueError("Trajectory action width differs")
        if (counts > session.env.config.control_decimation).any():
            raise ValueError("Invalid physical tick counts")
        # Validate every action before executing any; saved actions are canonical,
        # already clipped commands and must not be re-interpolated or re-run IK.
        for row in actions:
            session.robot.command(row)
        for row, count in zip(actions, counts):
            if not session._step(row) or session.tick_counts[-1] != count:
                raise ValueError("Replay terminated at a different physical tick")
        result = session.verdict()
    write_json(Path(output)/"result.json", result)
    return result


def verify_twice(instance, trajectory, output, *, live=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    config = json.loads(Path(instance).read_text())
    results = []
    for index in (1,2):
        folder = output / f"replay-{index}"
        if folder.exists():
            raise FileExistsError(f"Refusing stale replay evidence: {folder}")
        folder.mkdir()
        command = [sys.executable,"-m","topogym.benchmark","replay",str(instance),str(trajectory),str(folder)]
        if index == 2:
            command.append("--no-video")
        with (folder/"process.log").open("wb") as log:
            subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT,
                           timeout=float(config.get("replay_timeout_s",3600)))
        results.append(json.loads((folder/"result.json").read_text()))
    a,b = results
    deterministic = a["final_sha256"] == b["final_sha256"] and a["initial_sha256"] == b["initial_sha256"]
    if live is not None:
        deterministic = deterministic and live["final_sha256"] == a["final_sha256"] and live["initial_sha256"] == a["initial_sha256"]
    states=[json.loads((output/f"replay-{i}"/"final-state.json").read_text()) for i in (1,2)]
    if live is not None:
        states.append(json.loads((output/"live/final-state.json").read_text()))
    consistent=all(equivalent_states(states[0],s) for s in states[1:])
    success = consistent and all(r["success"] and r["scoring_eligible"] for r in results)
    if live is not None:
        success = success and live["success"] and live["scoring_eligible"] and live["reason"] != "error"
    import hashlib
    final = dict(finalized=True, success=bool(success), deterministic=bool(deterministic), replay_consistent=consistent,
        comparison=dict(algorithm="si-numeric-v1",atol=1e-9,rtol=1e-9), replays=results,
        live=live, instance_sha256=digest(config), trajectory_sha256=hashlib.sha256(Path(trajectory).read_bytes()).hexdigest(),
        n_actions=a["n_actions"], sim_steps=a["sim_steps"], control_steps=a["control_steps"], grader_error=0)
    write_json(output/"final.json", final)
    return final
