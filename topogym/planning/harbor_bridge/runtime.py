"""Runtime copied into a private solution; one existing Session owns all physics."""
from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys
import traceback

import numpy as np

from .actions import native_row, public_action
from .contracts import (BridgeError, check_session, digest, file_hashes, instance_binding, load_trajectory,
                        member, read_json, require_same_instance)


def verify_files(solution, recipe):
    if recipe.get("schema_version") != 1 or recipe.get("harbor_qualified") is not False:
        raise BridgeError("Expected an unqualified bridge candidate manifest")
    actual_names = set(file_hashes(solution)) - {"bridge_manifest.json"}
    if actual_names != set(recipe["files"]):
        raise BridgeError("Private reference file inventory changed")
    for name, expected in recipe["files"].items():
        if digest(member(solution, name)) != expected:
            raise BridgeError(f"Private reference file changed: {name}")


def private_imports(solution, recipe):
    """Private helpers may extend planning/, never shadow installed simulator code."""
    if not any(name.startswith("topogym/planning/") for name in recipe["files"]):
        return
    import topogym
    for name, module in tuple(sys.modules.items()):
        if name == "topogym.planning" or name.startswith("topogym.planning."):
            path = getattr(module, "__file__", None)
            if path is not None and not Path(path).resolve().is_relative_to(solution.resolve()):
                raise BridgeError(f"Reference would reuse non-bundled planning module: {name}")
    private_root = str(solution / "topogym")
    if private_root not in topogym.__path__:
        topogym.__path__.insert(0, private_root)


def execute(session, recipe, solution, output, *, instance_path=None):
    """Execute without assuming script completion implies Task success."""
    check_session(session, recipe["binding"], instance_path=instance_path)
    execution = recipe["execution"]
    kind = execution["kind"]
    if kind in {"public_trajectory", "native_trajectory"}:
        native = kind == "native_trajectory"
        rows, _ = load_trajectory(member(solution, execution["artifact"]), recipe["binding"], native=native)
        # Validate the ENTIRE stream before its first action. Do not discover a
        # lossy closing target halfway through a previously successful motion.
        rows = np.stack([(native_row if native else public_action)(session, row) for row in rows])
        for row in rows:
            if session.step(row):
                break
    elif kind == "script":
        path = member(solution, execution["script"])
        result = session.exec_code(path.read_text(), extra={"__file__": str(path)})
        if not result.get("ok"):
            raise BridgeError("Reference script failed: " + str(result.get("error")))
    elif kind == "session":
        module, name = execution["entrypoint"].split(":")
        callback = getattr(importlib.import_module(module), name)
        callback(session, output, **execution.get("kwargs", {}))
    else:
        raise BridgeError(f"Unsupported execution kind: {kind}")
    if not session.success():
        raise BridgeError("Reference completed without native Task success")


def run_privileged(solution, recipe, output, *, instance_path=Path("/app/instance.json"),
                   tooling_path=Path("/opt/tools/rcb_topogym.py")):
    require_same_instance(recipe["binding"], instance_binding(instance_path))
    if digest(tooling_path) != recipe["tooling_sha256"]:
        raise BridgeError("Installed task tooling differs from the packaged reference")
    sys.path.insert(0, str(tooling_path.parent))
    tooling = importlib.import_module("rcb_topogym")
    if Path(tooling.__file__).resolve() != tooling_path.resolve():
        raise BridgeError("Wrong task tooling was imported")
    if not callable(getattr(tooling, "_source", None)):
        raise BridgeError("Task tooling does not expose installed-source identity")
    require_same_instance(recipe["binding"]["instance"]["topogym_source"], tooling._source())
    private_imports(solution, recipe)
    session = tooling.Session(recipe["binding"]["instance"]["task"], instance=instance_path, strict=True)
    report = dict(status="running", harbor_qualified=False, execution=recipe["execution"]["kind"])
    try:
        check_session(session, recipe["binding"], instance_path=instance_path)
        env = session.env
        episode, branch, config = env._episode_id, env._branch_id, env.config
        session_config = json.loads(json.dumps(session.config))
        start_controls, start_ticks = env._control_step, env._world.physics_step
        session.record_start()
        recording = session._recording
        try:
            execute(session, recipe, solution, output, instance_path=instance_path)
            if (session.env is not env or env._episode_id != episode or env._branch_id != branch or session._resets != 0
                    or session._recording is not recording):
                raise BridgeError("Reference replaced the bound episode or the caller-owned recorder")
            require_same_instance(session_config, session.config)
            if env.config is not config:
                raise BridgeError("Reference replaced the frozen simulator configuration")
            if (len(recording) != session.n_steps or not recording
                    or env._control_step - start_controls != session.n_steps
                    or env._world.physics_step - start_ticks != session.physics_steps):
                raise BridgeError("Reference advanced physics outside the recorded Session")
            ticks = np.asarray(session._recorded_ticks)
            decimation = session.config["control_decimation"]
            if (ticks.shape != (len(recording),) or ticks.dtype.kind not in "iu"
                    or not np.all(ticks[:-1] == decimation) or not 1 <= ticks[-1] <= decimation
                    or int(ticks.sum()) != session.physics_steps):
                raise BridgeError("Reference changed the frozen control timing")
            report["status"] = "native_success_pending_harbor_verifier"
        except BaseException as error:
            report.update(status="failed", error=f"{type(error).__name__}: {error}")
            raise
        finally:
            # Evidence survives failure, but a failed callback still exits nonzero.
            if session._recording is recording:
                actions = session.record_stop()
                session.save_trajectory(actions, output / "trajectory.npz", meta=dict(
                    source="harbor_bridge", execution=recipe["execution"]["kind"],
                    instance_sha256=recipe["binding"]["instance_sha256"], status=report["status"]))
            report["session"] = session.status()
    except BaseException as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        (output / "bridge_report.json").write_text(json.dumps(report, indent=2) + "\n")
        session.close()


def stream_standard(robot, recipe, rows, *, connection_errors=(), episode_errors=()):
    """Public HTTP only; never append settling actions or change the reference rate."""
    instance = recipe["binding"]["instance"]
    spec = robot.spec()
    action = spec["action_types"]["joint_position"]
    dt = instance["simulator"]["physics_dt_s"] * instance["simulator"]["control_decimation"]
    if (action["layout"] != instance["action_layout"] or action["dim"] != instance["action_dim"]
            or not np.isclose(1. / spec["control_hz"], dt, rtol=0, atol=1e-12)):
        raise BridgeError("Standard service action layout or timing differs")
    published_limits = action["limits"]
    if isinstance(published_limits, dict):
        if set(published_limits) != set(action["layout"]):
            raise BridgeError("Standard service limits do not cover the frozen action layout")
        published_limits = [published_limits[name] for name in action["layout"]]
    limits = np.asarray(published_limits, dtype=float)
    if (limits.shape != (rows.shape[1], 2) or not np.isfinite(limits).all()
            or np.any(rows < limits[:, 0]) or np.any(rows > limits[:, 1])):
        raise BridgeError("Standard service would clip reference actions")
    status = robot.status()
    if status["control_steps"] != 0 or status["done"]:
        raise BridgeError("Standard reference requires a fresh episode")
    count = int(spec["max_chunk_s"] / dt + 1e-9)
    if count < 1:
        raise BridgeError("Standard service chunk budget is below one control period")
    cameras = spec.get("default_cameras") or list(spec["cameras"])
    if not cameras:
        raise BridgeError("Standard service publishes no camera")
    cursor = restarts = 0
    while cursor < len(rows):
        end = min(cursor + count, len(rows))
        try:
            result = robot.submit("joint_position", rows[cursor:end], dt=dt, interpolate="hold",
                                  cameras=cameras[:1], video="none", note=f"oracle rows {cursor}:{end}")
        except connection_errors:
            restarts += 1
            if restarts > 3:
                raise BridgeError("Standard service exceeded restart budget")
            status = robot.wait_ready(timeout=3600)
            completed = status["control_steps"]
            if type(completed) is not int or not cursor <= completed <= end:
                raise BridgeError("Restart ledger is outside the submitted reference prefix")
            cursor = completed
            if status["done"]:
                break
            continue
        except episode_errors:
            status = robot.status()
            completed = status["control_steps"]
            if type(completed) is not int or not cursor <= completed <= end:
                raise BridgeError("Terminal ledger is outside the submitted reference prefix")
            cursor = completed
            break
        meta = result.meta
        executed = meta["executed_rows"]
        if meta["n_clipped"] or type(executed) is not int or not 0 < executed <= end - cursor:
            raise BridgeError("Standard service clipped or rejected reference actions")
        if meta["control_steps_chunk"] != executed:
            raise BridgeError("Standard service changed reference control timing")
        cursor += executed
        if meta["done"]:
            status = robot.status()
            break
    else:
        status = robot.status()
    if type(status["control_steps"]) is not int or status["control_steps"] != cursor:
        raise BridgeError("Standard service final ledger differs from acknowledged reference rows")
    if not status["done"] or status["reason"] != "success":
        raise BridgeError("Standard reference ended without native Task success; no implicit holds added")
    return dict(status="native_success_pending_harbor_verifier", harbor_qualified=False,
                executed_rows=status["control_steps"], reference_rows=len(rows), restarts=restarts,
                identity_scope="frozen task package; HTTP verifies layout, rate and limits")


def main(solution=None):
    solution = Path(solution or "/solution")
    output = Path("/app/output")
    output.mkdir(parents=True, exist_ok=True)
    try:
        recipe = read_json(solution / "bridge_manifest.json")
        verify_files(solution, recipe)
        if recipe["mode"] == "privileged":
            run_privileged(solution, recipe, output)
        elif recipe["mode"] == "standard":
            import requests
            sys.path.insert(0, "/opt/tools")
            from rcb_client import Robot, EpisodeOver
            rows, _ = load_trajectory(member(solution, recipe["execution"]["artifact"]), recipe["binding"])
            report = stream_standard(Robot(), recipe, rows, connection_errors=(requests.exceptions.RequestException,),
                                     episode_errors=(EpisodeOver,))
            (output / "bridge_report.json").write_text(json.dumps(report, indent=2) + "\n")
        else:
            raise BridgeError("Unknown reference mode")
        return 0
    except BaseException as error:
        traceback.print_exc()
        path = output / "bridge_report.json"
        report = read_json(path) if path.is_file() else {}
        report.update(status="failed", harbor_qualified=False, error=f"{type(error).__name__}: {error}")
        path.write_text(json.dumps(report, indent=2) + "\n")
        return 1
