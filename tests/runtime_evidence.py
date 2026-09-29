"""Persistent evidence from the actual Env under test, including failed runs."""

from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import fields
from datetime import datetime, timezone
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
import json
import hashlib
import platform
import resource
import sys
import time
import traceback
import weakref

import numpy as np
from PIL import Image

from topogym.recording import RecordingSession
from topogym.recording.encoding import probe
from topogym.utils.io import to_jsonable, write_json_atomic

BASE_TASKS = (
    "cast_coil",
    "cast_keyhole",
    "horseshoe_ring",
    "hedgehog_in_cage",
    "interlocked_claws",
    "buzz_wire_3d",
    "lock_picking",
    "fiber_bundling",
    "blanket_flatten",
    "rope_threading",
    "knot_untying",
    "orbits",
    "slotted_post_ring",
)


def arrays(value, prefix=""):
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield from arrays(child, f"{prefix}/{key}")
    elif isinstance(value, np.ndarray) and value.dtype.kind in "fiu":
        yield prefix, value


def state_arrays(observation):
    return dict(arrays({k: observation[k] for k in ("world", "robot")}))


class RuntimeEvidence:
    def __init__(self, folder, task_id, config):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=False)
        self.started = time.monotonic()
        packages = {}
        import torch

        hardware = dict(cuda_available=torch.cuda.is_available())
        if hardware["cuda_available"]:
            hardware.update(
                device=torch.cuda.get_device_name(),
                total_memory_bytes=torch.cuda.get_device_properties(0).total_memory,
            )
        for name in ("genesis-world", "gs-nyx", "gs-nyx-plugin", "pyuipc", "numpy", "torch", "pytest"):
            try:
                packages[name] = version(name)
            except PackageNotFoundError:
                packages[name] = None
        self.report = dict(
            schema_version=1,
            started_at_utc=datetime.now(timezone.utc).isoformat(),
            task_id=task_id,
            status="running",
            config=to_jsonable(
                {f.name: getattr(config, f.name) for f in fields(config)}
            ),
            platform=platform.platform(),
            packages=packages,
            hardware=hardware,
            stages=[],
            samples=0,
            recordings=[],
            scope="selected setting lifecycle only; no planner, grasp or solvability claim",
        )
        self.recording = None
        self.sessions = []
        self.bound_envs = weakref.WeakSet()
        self.rows = (self.folder / "steps.jsonl").open("x")
        self.save()

    def save(self):
        self.report["wall_time_s"] = time.monotonic() - self.started
        self.report["peak_rss_bytes"] = int(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            * (1 if sys.platform == "darwin" else 1024)
        )
        write_json_atomic(self.folder / "report.json", self.report)

    @contextmanager
    def stage(self, name):
        row = dict(name=name, status="running")
        self.report["stages"].append(row)
        self.save()
        start = time.monotonic()
        try:
            yield row
        except BaseException:
            row.update(status="failed", traceback=traceback.format_exc())
            raise
        else:
            row["status"] = "passed"
        finally:
            row["wall_time_s"] = time.monotonic() - start
            self.save()

    def end_recording(self):
        if self.recording is None:
            return
        session, self.recording = self.recording, None
        if session.frame_count:
            session.finish(
                dict(
                    test_status=self.report["status"],
                    task_success=False,
                    scope="observed lifecycle test segment",
                )
            )
            session.close(commit=True)
            videos = {}
            for path in (session.output / "videos").glob("*.mp4"):
                videos[str(path.relative_to(self.folder))] = probe(path, decode=True)
            self.report["recordings"].append(
                dict(
                    path=str(session.output.relative_to(self.folder)),
                    videos=videos,
                    source_frames=session.source_count,
                )
            )
        else:
            session.close(commit=False)
        self.save()

    def sample(self, env, observation, info, *, action=None, label="step"):
        if env not in self.bound_envs:
            def event_sink(event):
                with (self.folder / "history_events.jsonl").open("a") as events:
                    events.write(json.dumps(to_jsonable(event)) + "\n")
                for session in self.sessions:
                    session.on_lifecycle(event)
            env.add_lifecycle_sink(event_sink)
            self.bound_envs.add(env)
        observation = dict(observation, world=env.privileged.get("world"), robot=env.privileged.get("robot"))
        identity = (info["episode_id"], info["branch_id"])
        from topogym.sensors.renderers.nyx import NyxCamera

        presentation = to_jsonable(env._world.tabletop.presentation)
        presentation["cameras"] = {
            name: type(camera).__name__ for name, camera in env._world.cameras.items()
        }
        presentation["camera_settings"] = {
            name: {
                **{key: to_jsonable(getattr(camera.sensor._options, key))
                   for key in ("res", "pos", "lookat", "fov", "spp", "denoise", "model")},
                **{key: str(getattr(camera.sensor._options, key))
                   for key in ("render_mode", "anti_aliasing", "tone_mapper")},
            }
            for name, camera in env._world.cameras.items()
            if isinstance(camera, NyxCamera)
        }
        self.report["presentation"] = presentation
        self.save()
        assert presentation["renderer"] == "nyx"
        assert presentation["background"] == "compact_lab"
        assert env._world.cameras and all(
            isinstance(camera, NyxCamera) for camera in env._world.cameras.values()
        ), "Runtime RGB must come from actual Nyx cameras"
        frame = env.sensor_frame()
        expected_cameras = ({"cam_high", "cam_low", "cam_left_wrist", "cam_right_wrist"}
                            if env.action_spec["robot_id"] == "aloha" else {"agentview", "front_oblique", "wrist"})
        assert set(frame.rgb) == expected_cameras
        assert all(image.shape == (480, 848, 3) for image in frame.rgb.values())
        if not self.report["samples"]:
            frame_folder = self.folder / "initial_frames"
            frame_folder.mkdir()
            self.report["initial_frames"] = {}
            for name, pixels in frame.rgb.items():
                path = frame_folder / f"{name}.png"
                Image.fromarray(pixels).save(path)
                self.report["initial_frames"][name] = dict(
                    path=str(path.relative_to(self.folder)),
                    width=pixels.shape[1], height=pixels.shape[0],
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    state_id=info["state_id"],
                )
            self.save()
        if self.recording is not None and self.recording.identity != identity:
            self.end_recording()
        if self.recording is None:
            self.recording = RecordingSession(
                self.folder / f"branch_{len(self.report['recordings']):03d}",
                fps=30,
                metadata=dict(
                    episode=to_jsonable(env.episode_metadata),
                    presentation=presentation,
                    scope="actual test execution",
                ),
            )
            self.recording.__enter__()
            self.sessions.append(self.recording)
        self.recording.append(frame)
        values = state_arrays(observation)
        index = self.report["samples"]
        np.savez_compressed(self.folder / f"state_{index:04d}.npz", **values)
        nonfinite = [
            name for name, value in values.items() if not np.isfinite(value).all()
        ]
        saved = env._history.get(info["state_id"]).world
        if label == "initial":
            capacities = env._world.scene.sim.rigid_solver.collider._collider_info
            self.report["rigid_collision_capacity"] = {
                name: int(getattr(capacities, name)[None])
                for name in ("max_collision_pairs", "max_collision_pairs_broad",
                             "max_candidate_contacts", "max_contacts")
            }

            def size(value):
                if isinstance(value, dict):
                    return sum(size(x) for x in value.values())
                if hasattr(value, "element_size"):
                    return value.numel() * value.element_size()
                return value.nbytes

            def stored_size(value):
                if isinstance(value, dict):
                    return sum(stored_size(x) for x in value.values())
                return getattr(value, "stored_nbytes", size(value))

            inventory = [
                dict(
                    path=b.path,
                    kind=b.kind,
                    bytes=size(b.value),
                    stored_bytes=stored_size(b.value),
                )
                for b in saved.buffers
            ]
            self.report["checkpoint_buffers"] = sorted(
                inventory, key=lambda b: -b["bytes"]
            )
        native = saved.ipc_state
        # A finite falling rope is not sufficient evidence of table support.
        # Check vertices over the table footprint; falling off an edge is a
        # different task behaviour and must not be mistaken for penetration.
        table = env._world.tabletop
        low, high = (
            table.robot_footprint.table_min_xy,
            table.robot_footprint.table_max_xy,
        )
        table_z = table.frames.table_surface_origin[2]
        clearances = {}
        for name, state in observation["world"].get("fem", {}).items():
            positions = state["position_m"]
            inside = (
                (positions[:, :2] > np.asarray(low) + 1e-3)
                & (positions[:, :2] < np.asarray(high) - 1e-3)
            ).all(axis=1)
            if inside.any():
                clearances[name] = float(positions[inside, 2].min() - table_z)
        checkpoints = None
        if native is not None:
            checkpoints = dict(
                native_frame=native.frame,
                numeric_geometry_attributes=len(native.attributes),
                native_files={
                    name: dict(
                        compressed_bytes=len(data),
                        sha256=hashlib.sha256(data).hexdigest(),
                    )
                    for name, data in native.files
                },
            )
        contacts = observation["world"]["contacts"]
        penetration = contacts.get("penetration", np.empty(0))
        link_names = {
            link.idx: f"{name}/{link.name}"
            for name, entity in env._world.entities.items()
            for link in getattr(entity, "links", ())
        }
        worst_contacts = [
            dict(
                penetration_m=float(penetration[i]),
                link_a=link_names[int(contacts["link_a"][i])],
                link_b=link_names[int(contacts["link_b"][i])],
            )
            for i in np.argsort(penetration)[-5:][::-1]
        ]
        row = dict(
            index=index,
            label=label,
            info=to_jsonable(info),
            terminal=to_jsonable(env.episode_metadata.get("terminal", {})),
            task_result=to_jsonable(env._task.get_state()),
            contact_events=to_jsonable(observation["world"].get("contact_events")),
            action=to_jsonable(action),
            nonfinite=nonfinite,
            state_file=f"state_{index:04d}.npz",
            ipc=to_jsonable(observation["world"].get("ipc", {})),
            checkpoint=checkpoints,
            fem_table_clearance_m=clearances,
            worst_rigid_contacts=worst_contacts,
            rigid_penetration_limit_m=0.001,
            shapes={name: list(value.shape) for name, value in values.items()},
            maxima={
                name: float(np.max(np.abs(value), initial=0))
                if np.isfinite(value).all()
                else None
                for name, value in values.items()
            },
            camera_metadata=to_jsonable(frame.camera_metadata),
        )
        self.rows.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        self.rows.flush()
        self.report["samples"] += 1
        self.report["last_info"] = to_jsonable(info)
        self.save()
        assert not nonfinite, f"Non-finite simulated state: {nonfinite}"
        assert np.max(penetration, initial=0) <= 0.001, (
            f"Rigid penetration exceeds 1 mm: {worst_contacts}"
        )
        assert frame.physics_step == info["physics_step"]
        assert frame.state_id == info["state_id"]
        ipc = observation["world"].get("ipc", {})
        if ipc:
            assert ipc["native_valid"]
            assert all(value >= -1e-4 for value in clearances.values()), (
                f"FEM penetrated the tabletop: {clearances}"
            )
            ownership = ipc["contact_ownership"]
            assert ownership["rigid_robot_self_pairs"] > 0, (
                "Robot self-contact was lost"
            )
            assert ownership["rigid_robot_table_pairs"] > 0, (
                "Robot/table contact was lost"
            )
            assert ownership["rigid_native_body_pairs"] == 0, (
                "Native bodies have duplicate collision ownership"
            )
            assert (
                ipc["native_frame"] == info["physics_step"] * env.config.solver_substeps
            )
            for residual in ipc["attachment_residual_m"].values():
                assert residual < 0.001, f"Permanent attachment separated: {residual} m"
            for ratio in ipc.get("volume_ratio", {}).values():
                assert (
                    np.isfinite(list(ratio.values())).all() and ratio["minimum"] > 0
                ), "Inverted FEM element"
        for name, value in values.items():
            if name.endswith("velocity_m_s"):
                assert np.max(np.abs(value), initial=0) < 25, (
                    f"Unphysical speed: {name}"
                )
        return values

    def close(self, error=None):
        self.report["status"] = "failed" if error else "passed"
        if error:
            self.report["traceback"] = error
        try:
            self.end_recording()
        except BaseException:
            self.report.update(status="failed", recording_error=traceback.format_exc())
            if not error:
                raise
        finally:
            self.rows.close()
            self.save()
