"""Private RoboRSI environment/skills owner and lossless controller journal."""
from __future__ import annotations

import base64
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import random
import sqlite3
import subprocess
import time

import numpy as np
from PIL import Image

from humanclaw_bench.experiments.recorder import event, span
from .protocol import digest


class ControlBudgetReached(RuntimeError):
    """Signal a declared controller-step limit before another action executes."""
    pass


def image_block(array):
    """Encode an RGB camera array using the shared JPEG observation contract."""
    stream = io.BytesIO()
    Image.fromarray(np.asarray(array, dtype=np.uint8)).save(stream, format="JPEG", quality=95, subsampling=2)
    return {"type": "image", "mimeType": "image/jpeg", "data": base64.b64encode(stream.getvalue()).decode()}


def plain(value):
    """Convert NumPy values and paths to ordinary JSON-compatible containers."""
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


def restore_array(target, value):
    """JSON loses trailing dimensions of empty arrays (e.g. MuJoCo (0, 3))."""
    array = np.asarray(value, dtype=target.dtype)
    if array.size != target.size:
        raise ValueError(f"Snapshot shape incompatible with simulator: {array.shape} vs {target.shape}")
    target[:] = array.reshape(target.shape)


def source_identity(root):
    """Hash the shipped RoboRSI sources and identify their upstream baseline."""
    root = Path(root)
    files = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted((root / "roborsi").rglob("*"))
             if p.is_file() and p.suffix in {".py", ".md", ".json", ".yaml", ".toml"}}
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root,
                                         stderr=subprocess.DEVNULL, text=True).strip()
    except subprocess.SubprocessError:
        commit = (root / "UPSTREAM_COMMIT").read_text().strip() if (root / "UPSTREAM_COMMIT").exists() else None
    return {"upstream_commit": commit, "source_tree_sha256": digest(files), "files": files}


class MotionJournal:
    """One SQLite file, including durable pre-execution intent for every step."""
    def __init__(self, directory):
        """Create the durable single-writer control journal."""
        self.path = Path(directory) / "motion.sqlite"
        self.db = sqlite3.connect(self.path)
        # Reuse the rollback journal: GPFS create/unlink latency must not be
        # paid twice per control step. FULL durability is retained; no WAL
        # shared-memory assumptions are introduced on the network filesystem.
        self.db.execute("PRAGMA journal_mode=PERSIST")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE steps (id INTEGER PRIMARY KEY, phase TEXT, span_id TEXT, "
                        "action TEXT, before_state TEXT, after_state TEXT, status TEXT, elapsed_ns INTEGER)")
        self.db.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT)")

    def metadata(self, key, value):
        """Persist a reproducibility record in the control journal."""
        self.db.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)", (key, json.dumps(plain(value))))
        self.db.commit()

    def begin(self, phase, action, before):
        """Commit control intent before forwarding an action to the simulator."""
        row = event("control.step.start", kind="environment", name="controller.step",
                    data={"journal": "motion.sqlite", "phase": phase})
        cursor = self.db.execute("INSERT INTO steps (phase,span_id,action,before_state,status) VALUES (?,?,?,?,?)",
                                (phase, row.get("span_id") if row else None,
                                 json.dumps(plain(action)), json.dumps(plain(before)), "started"))
        self.db.commit()
        return cursor.lastrowid

    def end(self, ident, after, elapsed, status="completed"):
        """Persist the observed post-step state and execution status."""
        self.db.execute("UPDATE steps SET after_state=?,status=?,elapsed_ns=? WHERE id=?",
                        (json.dumps(plain(after)), status, elapsed, ident))
        self.db.commit()
        event("control.step.end", kind="environment", name="controller.step",
              data={"journal": "motion.sqlite", "row_id": ident, "status": status, "duration_ms": elapsed/1e6})

    def close(self):
        """Close the journal connection after the last committed operation."""
        self.db.close()


class RoboBackend:
    """Own the private simulator, released skills and actual control boundary."""
    def __init__(self, task, seed, directory, *, roboroot, resolution=256, settle_steps=20,
                 max_control_steps=20000):
        """Reset the fixed task, snapshot its state and resolve the public catalog."""
        self.task, self.seed = task, int(seed)
        random.seed(self.seed)
        np.random.seed(self.seed)
        self.directory = Path(directory)
        self.roboroot = Path(roboroot).resolve()
        self.resolution = resolution
        self.control_steps, self.max_control_steps = 0, max_control_steps
        self.phase = "initialization"
        self.journal = MotionJournal(directory)
        os.environ["ROBORSI_CURRENT_SIM_TASK"] = task
        from roborsi.embodied.sim.libero.adapter import LiberoProBackend
        from roborsi.runtime_mode import current_mode
        if current_mode().value not in {"frozen", "eval"}:
            raise ValueError("Shared skill service requires frozen mode")
        with span("environment.startup", kind="environment", input={"task": task, "seed": seed}):
            import torch
            torch.manual_seed(self.seed)
            from unittest.mock import patch
            from .provenance import file_hash
            loaded_files, original_load = {}, torch.load
            def tracked_load(path, *args, **kwargs):
                """Record the exact initialization files read by the upstream loader."""
                if isinstance(path, (str, Path)) and Path(path).is_file():
                    loaded_files[str(Path(path).resolve())] = file_hash(path)
                return original_load(path, *args, **kwargs)
            with patch.object(torch, "load", tracked_load):
                self.env = LiberoProBackend().make_env(task, {"camera_heights": resolution,
                    "camera_widths": resolution, "settle_steps": settle_steps, "require_depth": True})
            self.loaded_init_files = loaded_files
            self._raw_step = self.env._env.step
            self.env._env.step = self._recorded_step
            self.env.reset(seed)
            self.initial_snapshot = self.snapshot()
        self.phase = "episode"
        self.instruction = self.env.instruction
        self.initial_state_index = self.seed % len(self.env._init_states)
        rs = self.env._env.env
        scene_xml = rs.model.get_xml()
        (self.directory / "scene.xml").write_text(scene_xml)
        self.scene_sha256 = hashlib.sha256(scene_xml.encode()).hexdigest()
        self.bddl = {"path": str(rs.bddl_file_name), "sha256": file_hash(rs.bddl_file_name)}
        self.journal.metadata("initial", {"task": task, "seed": seed,
            "initial_state_index": self.initial_state_index, "initial_state_count": len(self.env._init_states),
            "settle_steps": settle_steps, "snapshot": self.initial_snapshot,
            "controller": "JOINT_POSITION", "action_dimension": 8, "action_dtype": "float64",
            "action_semantics": "7 normalized joint controller inputs plus gripper; actual forwarded input",
            "resolution": resolution, "scene_sha256": self.scene_sha256})
        self.source = source_identity(roboroot)
        from roborsi.embodied.agent_loop.prompt_tools import _build_tool_specs
        from roborsi.embodied.agent_loop.vlm_io import _sanitize_openai_tool
        self.catalog = [_sanitize_openai_tool(spec)["function"]
                        for spec in _build_tool_specs(ns="libero", task="libero_pick_place")]
        from roborsi.embodied.skills import get_ns, discover_compounds
        compounds = {s.name: s for s in discover_compounds("libero_pick_place")}
        for spec in self.catalog:
            skill = get_ns(spec["name"], "libero") or compounds.get(spec["name"])
            if skill is not None:
                implementation = skill.path.parent / "policy.py"
                spec["provenance"] = {"declaration": str(skill.path.resolve().relative_to(self.roboroot)),
                    "implementation": str(implementation.resolve().relative_to(self.roboroot)),
                    "implementation_sha256": hashlib.sha256(implementation.read_bytes()).hexdigest() if implementation.exists() else None}
        self.knowledge = self._knowledge()
        self.catalog_hash = digest({"catalog": self.catalog, "source": self.source["source_tree_sha256"],
                                    "knowledge": self.knowledge, "task": task})
        self.journal.metadata("catalog_hash", self.catalog_hash)
        from roborsi.embodied.agent_loop.rollout import DispatchContext
        workdir = self.directory / "service_artifacts"
        workdir.mkdir()
        self.context = DispatchContext(env=self.env, workdir=workdir, last_image_path=None,
                                       ns="libero", task="libero_pick_place")

    def _knowledge(self):
        """Load the released task wiki and seed plan for all four arms."""
        from roborsi.agents.memory.task_wiki import read_wiki
        from roborsi.agents.roles.planner import persistent_plan_input
        wiki = read_wiki("libero_pick_place")
        path, source = persistent_plan_input("libero_pick_place")
        plan = path.read_text() if path.is_file() else ""
        return f"TASK WIKI:\n{wiki}\nRELEASED PLAN ({source}):\n{plan}"

    def state(self):
        """Copy simulator state used to check each recorded control step."""
        data = self.env._env.env.sim.data
        return {"time": float(data.time), "qpos": np.array(data.qpos).copy(),
                "qvel": np.array(data.qvel).copy(), "act": np.array(data.act).copy()}

    def snapshot(self):
        """Capture simulator, controller, gripper and random-generator state."""
        rs = self.env._env.env
        snapshot = self.state()
        snapshot["sim_state"] = np.asarray(rs.sim.get_state().flatten()).copy()
        snapshot["data"] = {name: np.asarray(getattr(rs.sim.data, name)).copy()
                            for name in ("ctrl", "qacc_warmstart", "mocap_pos", "mocap_quat", "userdata")
                            if hasattr(rs.sim.data, name)}
        controller = rs.robots[0].controller
        fields = ("goal_qpos", "joint_pos", "joint_vel", "kp", "kd", "output_min", "output_max", "input_min", "input_max")
        snapshot["controller"] = {name: plain(getattr(controller, name)) for name in fields
                                  if hasattr(controller, name) and getattr(controller, name) is not None}
        snapshot["counters"] = {name: getattr(rs, name) for name in ("timestep", "cur_time", "done") if hasattr(rs, name)}
        gripper = rs.robots[0].gripper
        if hasattr(gripper, "current_action"):
            snapshot["gripper_current_action"] = plain(gripper.current_action)
        snapshot["rng"] = {"python": random.getstate(), "numpy": np.random.get_state()}
        try:
            import torch
            snapshot["rng"]["torch_cpu"] = torch.get_rng_state().tolist()
            if torch.cuda.is_initialized():
                snapshot["rng"]["torch_cuda"] = [s.tolist() for s in torch.cuda.get_rng_state_all()]
        except ImportError:
            pass
        return plain(snapshot)

    def restore(self, snapshot):
        """Restore a saved state and refresh the public observation caches."""
        rs = self.env._env.env
        rs.sim.set_state_from_flattened(np.asarray(snapshot["sim_state"], dtype=float))
        for key, value in snapshot.get("data", {}).items():
            restore_array(getattr(rs.sim.data, key), value)
        rs.sim.forward()
        controller = rs.robots[0].controller
        for key, value in snapshot.get("controller", {}).items():
            setattr(controller, key, np.asarray(value) if isinstance(value, list) else value)
        for key, value in snapshot.get("counters", {}).items():
            setattr(rs, key, value)
        if "gripper_current_action" in snapshot:
            rs.robots[0].gripper.current_action = np.asarray(snapshot["gripper_current_action"])
        def tuples(value):
            """Restore tuple containers required by the Python random generator."""
            return tuple(tuples(x) for x in value) if isinstance(value, list) else value
        random.setstate(tuples(snapshot["rng"]["python"]))
        n = snapshot["rng"]["numpy"]
        np.random.set_state((n[0], np.array(n[1], dtype=np.uint32), n[2], n[3], n[4]))
        if "torch_cpu" in snapshot["rng"]:
            import torch
            torch.set_rng_state(torch.tensor(snapshot["rng"]["torch_cpu"], dtype=torch.uint8))
            if "torch_cuda" in snapshot["rng"]:
                torch.cuda.set_rng_state_all([torch.tensor(v, dtype=torch.uint8) for v in snapshot["rng"]["torch_cuda"]])
        from roborsi.embodied.sim.libero.adapter import _visible_raw_obs, _to_sim_obs
        raw = rs._get_observations(force_update=True)
        self.env._raw = _visible_raw_obs(raw)
        self.env._last_obs = _to_sim_obs(raw, self.env.instruction)
        self.env._invalidate_sensor_consumers()
        # Forward/observation refresh can overwrite solver warm-start inputs.
        # Restore them last: tiny first-step differences can amplify at contact.
        # Mocap inputs were also restored before forward for derived geometry.
        for key, value in snapshot.get("data", {}).items():
            restore_array(getattr(rs.sim.data, key), value)

    def _recorded_step(self, action):
        """Journal the exact finite eight-dimensional command at the env boundary."""
        action = np.asarray(action, dtype=np.float64).reshape(-1)
        if action.shape != (8,) or not np.isfinite(action).all():
            raise ValueError("Expected finite 8-D JOINT_POSITION controller input")
        if self.phase == "episode" and self.control_steps >= self.max_control_steps:
            raise ControlBudgetReached("Episode controller-step budget exhausted before next step")
        before = self.state()
        ident = self.journal.begin(self.phase, action, before)
        started = time.monotonic_ns()
        try:
            result = self._raw_step(action)
        except BaseException:
            self.journal.end(ident, self.state(), time.monotonic_ns()-started, "indeterminate")
            raise
        if self.phase == "episode":
            self.control_steps += 1
        self.journal.end(ident, self.state(), time.monotonic_ns()-started)
        return result

    def observe(self):
        """Return shared camera images and robot-only proprioception."""
        obs = self.env.take_snapshot()
        images = []
        for name in ("head_camera", "wrist"):
            if name in obs.images:
                images.append(image_block(obs.images[name]))
        raw = self.env.raw_obs()
        proprio = {key: plain(raw[key]) for key in ("robot0_joint_pos", "robot0_joint_vel", "robot0_eef_pos", "robot0_eef_quat", "robot0_gripper_qpos") if key in raw}
        names = [k for k in ("head_camera", "wrist") if k in obs.images]
        path = getattr(getattr(self, "context", None), "last_image_path", None)
        if path and Path(path).is_file() and Path(path).name not in {
                "look_head_camera.jpg", "look_wrist.jpg", "view_head_camera.jpg", "view_wrist.jpg"}:
            images.append(image_block(np.asarray(Image.open(path).convert("RGB"))))
            names.append("requested_view:" + Path(path).name)
        return {"images": images, "camera_names": names,
                "proprioception": proprio, "control_steps": self.control_steps}

    def dispatch(self, name, arguments):
        """Invoke the registered upstream skill implementation."""
        if name == "done":
            return {"acknowledged": True, "agent_claim": arguments}
        from roborsi.embodied.agent_loop.rollout import _dispatch
        result, _ = _dispatch(self.context, {"tool": name, "args": arguments})
        return plain(result)

    def success(self):
        """Evaluate the private simulator predicate outside agent decisions."""
        with span("evaluator.success", kind="evaluator") as operation:
            result = self.env.check_success()
            if result is None:
                raise RuntimeError("Simulator did not return a success verdict")
            operation.set_output({"success": bool(result)})
            return bool(result)

    def manifest(self):
        """Describe the actual tools, assets, controller and observation contract."""
        versions = {}
        for package in ("roborsi", "mujoco", "robosuite", "numpy", "torch", "openai", "transformers"):
            try:
                versions[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                versions[package] = None
        return {"task": self.task, "seed": self.seed, "initial_state_index": self.initial_state_index,
                "catalog_hash": self.catalog_hash, "catalog": self.catalog, "source": self.source,
                "versions": versions, "knowledge_sha256": digest(self.knowledge),
                "bddl": self.bddl, "loaded_init_files": self.loaded_init_files,
                "controller": "JOINT_POSITION", "action_dimension": 8,
                "observation_contract": {"cameras": ["head_camera", "wrist"], "width": self.resolution,
                    "height": self.resolution, "encoding": "JPEG", "quality": 95, "subsampling": 2,
                    "proprioception_fields": ["robot0_joint_pos", "robot0_joint_vel", "robot0_eef_pos", "robot0_eef_quat", "robot0_gripper_qpos"],
                    "depth": "Available only through the same published server-side perception skills"},
                "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"), "scene_sha256": self.scene_sha256,
                "controller_config": self.initial_snapshot["controller"],
                "perception_configuration": {k: os.environ.get(k) for k in (
                    "ROBORSI_OWLV2_MODEL", "ROBORSI_POINT_SAM_MODEL", "ROBORSI_GROUNDING_DINO_MODEL",
                    "ROBORSI_PERCEPTION_MODEL", "ROBORSI_PERCEPTION_DEVICE", "ROBORSI_GRASP_FIX",
                    "ROBORSI_SAM3_PORT", "ROBORSI_PYROKI_PORT", "GRASPGEN_HOST", "GRASPGEN_PORT")}}

    def close(self):
        """Release the simulator and its motion journal."""
        self.env._env.step = self._raw_step
        self.env.close()
        self.journal.close()


class MockBackend:
    """Deterministic protocol fixture; never presented as a benchmark rollout."""
    def __init__(self):
        """Create a deterministic synthetic robot for protocol checks."""
        self.control_steps, self.position = 0, 0.0
        self.instruction, self.knowledge = "Move to position 2", ""
        self.catalog = [
            {"name": "look", "description": "Observe", "parameters": {"type": "object", "properties": {}}},
            {"name": "move", "description": "Move by delta", "parameters": {"type": "object", "properties": {"delta": {"type": "number"}}, "required": ["delta"], "additionalProperties": False}},
            {"name": "done", "description": "Finish", "parameters": {"type": "object", "properties": {"success": {"type": "boolean"}}, "required": ["success"]}},
        ]
        self.catalog_hash = digest(self.catalog)

    def observe(self):
        """Return a synthetic image and the current test position."""
        return {"images": [image_block(np.zeros((16, 16, 3), dtype=np.uint8))], "proprioception": {"position": self.position}}

    def dispatch(self, name, arguments):
        """Apply the small deterministic action set used by transport tests."""
        if name == "move":
            self.position += arguments["delta"]
            self.control_steps += 1
        return {"ok": True}

    def success(self):
        """Check the synthetic target without claiming a benchmark outcome."""
        return self.position == 2
