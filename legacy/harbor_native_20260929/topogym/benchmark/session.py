"""One manager-owned Env for a frozen benchmark instance.

Unlimited actors may construct a Session and reset the same instance. Limited
actors only receive the HTTP projection in service.py. Neither path executes
submitted Python in the simulator service.
"""
from contextlib import ExitStack
import json
from pathlib import Path
import time
import numpy as np

from . import PROTOCOL
from .client import EpisodeOver, Result
from .evidence import digest, fingerprint, plain, write_json
from .frames import Frames
from .requests import validate
from .robot import RobotModel
from . import wire


class Session:
    def __init__(self, instance="/app/instance.json", *, output="/app/output", record=True, env_factory=None):
        self.instance = json.loads(Path(instance).read_text()) if isinstance(instance, (str, Path)) else plain(instance)
        self.identity = digest(self.instance)
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.stack = ExitStack()
        self.record = record
        self.recording = None
        self.resets = -1
        config = dict(self.instance["simulator"])
        if config.get("seed") is None:
            raise ValueError("Benchmark instances require an explicit frozen seed")
        if config.get("control_mode", "JOINT_ABS") != "JOINT_ABS" or config.get("max_physics_steps") is not None:
            raise ValueError("Benchmark uses canonical joint targets and no episode step cap")
        if self.instance.get("fixture") == "cube_pick_place":
            from topogym.benchmark.fixtures.cube_pick_place import register_cube_pick_place
            self.stack.enter_context(register_cube_pick_place())
        elif self.instance.get("fixture"):
            raise ValueError("Unknown fixture")
        from topogym.simulator.config import SimulatorConfig
        from topogym.simulator.env import Env
        self.env = (env_factory or Env)(SimulatorConfig(**config))
        self.stack.callback(self.env.close)
        try:
            self.reset()
        except BaseException:
            self.stack.close()
            raise

    def _end_recording(self):
        if self.recording is not None:
            self.env.remove_frame_sink(self.recording.append)
            try:
                self.recording.append_final(self.env.sensor_frame())
                self.recording.finish(self.verdict())
                self.recording.close(commit=True)
            finally:
                self.recording.close(commit=False)
                self.recording = None

    def reset(self):
        self._end_recording()
        self.env.reset(seed=self.instance["simulator"]["seed"])
        self.robot = RobotModel(self.env._robot, self.env.timing_spec)
        self.started = time.monotonic()
        self.resets += 1
        self.rows = self.calls = self.control_steps = self.physics_steps = 0
        self.done, self.reason = False, None
        self.actions, self.tick_counts = [], []
        self.initial = fingerprint(self.env)
        self.spec = self._specification()
        self.log_path = self.output / f"episode-{self.resets}.jsonl"
        write_json(self.output / "identity.json", dict(instance_sha256=self.identity, initial_sha256=self.initial,
                   instance=self.instance, episode=plain(self.env.episode_metadata)))
        if self.record and self.env.config.enable_rgb:
            from topogym.recording import RecordingSession
            self.recording = RecordingSession(self.output / f"recording-{self.resets}", fps=30,
                metadata=dict(instance_sha256=self.identity, initial_sha256=self.initial, purpose="benchmark evidence"))
            self.recording.__enter__()
            self.recording.append(self.env.sensor_frame())
            self.env.add_frame_sink(self.recording.append)
        self._log("reset", initial_sha256=self.initial, reset_count=self.resets)
        return self.env.observe()

    def _specification(self):
        from topogym.config.scene import load_scene_config
        from topogym.sensors.camera_info import camera_contract
        robot, kinematics, types = self.robot.specifications()
        cameras = {}
        configs = load_scene_config(self.env.config).env.cameras
        for name, c in camera_contract(configs).items():
            if name not in self.env.sensor_frame().rgb:
                continue
            if c["motion"] == "fixed":
                mount = dict(type="static", extrinsic_cv=np.array(c["T_camera_cv_from_world"])[:3].tolist(),
                    cam2world_gl=(np.array(c["T_world_from_camera_cv"]) @ np.diag([1.,-1.,-1.,1.])).tolist())
            else:
                mount = dict(type="link", parent_link=c["parent_link"], link_T_cam_cv=c["T_parent_link_from_camera_cv"])
            cameras[name] = dict(image_size=c["resolution_px"], intrinsic_cv=c["K_px"], mount=mount,
                depth=self.env.config.enable_depth, depth_range_m=[c["clipping_m"][0], min(65.535,c["clipping_m"][1])])
        return dict(protocol=PROTOCOL, protocol_compat=["rcb-limited/2.0","rcb-limited/2.1"], simulator="TopoGym / Genesis 1.2.1",
            robot=robot["name"], task_text=self.instance["instruction"], static={},
            control_hz=1/self.env.timing_spec["control_dt_s"], physics_substeps=self.env.config.control_decimation,
            frame_time_semantics="frame_step/control_hz; meta.sim_time_s reports actual physical time, including a terminal partial control step",
            max_chunk_s=10., max_watch_s=30., video_fps=min(30.,1/self.env.timing_spec["control_dt_s"]), cameras=cameras, default_cameras=list(cameras),
            action_types=types, proprio_layout=self.robot.layout, proprio_groups=self.robot.proprio_groups,
            robot_spec=robot, kinematics=kinematics,
            budget=dict(reset=0, steps=None, wall_clock_s=self.instance.get("wall_clock_s",5400)),
            world=dict(frame="fixed simulator world, right-handed; robot base pose defines its placement", up="+z",
                units=dict(length="m",angle="rad",time="s"), quaternion_order="wxyz", camera_axes="OpenCV: +x right, +y down, +z forward"),
            depth=dict(modes=["none","last","frames"], default="none", kind="z-depth", unit="m", invalid=0,
                max_m=65.535, frames_encoding="uint16 mm, zlib", noise="off",
                renderer="Genesis geometric depth at the Nyx camera rig; RGB uses Nyx only"))

    def _log(self, event, **data):
        from .evidence import json_bytes
        with self.log_path.open("ab") as stream:
            stream.write(json_bytes(dict(event=event, control_steps=self.control_steps, physics_steps=self.physics_steps, **data))+b"\n")

    def status(self):
        elapsed = time.monotonic()-self.started
        if not self.done and elapsed >= self.spec["budget"]["wall_clock_s"]:
            self.done, self.reason = True, "timeout"
        return dict(step=self.rows, calls=self.calls, control_steps=self.control_steps, done=self.done, reason=self.reason, elapsed_s=elapsed)

    def _meta(self):
        status = self.status()
        return dict(**status, physics_steps=self.physics_steps, sim_time_s=self.env.sensor_frame().sim_time_s,
            time_s=status["elapsed_s"], time_left_s=max(0., self.spec["budget"]["wall_clock_s"]-status["elapsed_s"]))

    def _step(self, target):
        if self.status()["done"]:
            return False
        try:
            _,_,terminated,truncated,info = self.env.step(self.robot.command(target))
            self.actions.append(np.asarray(target, dtype=np.float64).copy())
            self.tick_counts.append(int(info["physics_steps"]))
            self.control_steps += 1
            self.physics_steps += int(info["physics_steps"])
            if terminated or truncated:
                self.done = True
                self.reason = "success" if info["task_success"] else "task_failed"
            return True
        except BaseException:
            self.done, self.reason = True, "error"
            raise

    def execute(self, meta, parts=(), *, submit=False):
        request = validate(meta, dict(parts), self.spec, submit=submit)
        if submit and self.status()["done"]:
            raise EpisodeOver("Episode has ended")
        self.calls += 1
        frames = Frames(request, self)
        try:
            return self._execute(request, frames, submit=submit)
        except BaseException:
            self.done, self.reason = True, "error"
            raise
        finally:
            frames.close()

    def _execute(self, request, frames, *, submit):
        frames.capture(force=True)
        before_control, before_physics = self.control_steps, self.physics_steps
        executed, plan = 0, []
        if submit:
            for i, row in enumerate(request.rows):
                if self.status()["done"]:
                    break
                target = row
                if request.action_type == "ee_pose":
                    target, result = self.robot.ee_command(row)
                    plan.append(dict(row=i, **result))
                start = self.robot.targets()
                row_started = False
                for tick in range(1, request.ticks+1):
                    command = target.copy()
                    if request.action_type == "joint_position" and request.interpolate == "linear":
                        command = start+(target-start)*tick/request.ticks
                        command[self.robot.gripper_columns] = target[self.robot.gripper_columns]
                    if not self._step(command):
                        break
                    row_started = True
                    frames.capture()
                if row_started:
                    executed += 1
                    self.rows += 1
        else:
            for _ in range(request.ticks):
                if not self._step(self.robot.targets()):
                    break
                frames.capture()
        extras = (dict(chunk_id=self.calls, type=request.action_type, executed_rows=executed,
            control_steps_chunk=self.control_steps-before_control, physics_steps_chunk=self.physics_steps-before_physics,
            clipped=request.clipped, n_clipped=len(request.clipped), plan=plan, ok=all(r["ok"] for r in plan)) if submit else
            dict(obs_id=self.calls, seconds=request.ticks/self.spec["control_hz"],
                 control_steps_watch=self.control_steps-before_control, physics_steps_watch=self.physics_steps-before_physics))
        self._log("submit" if submit else "observe", **extras)
        return frames.encode(dict(**self._meta(), **extras))

    def get_obs(self, **options):
        raw = self.execute(options)
        return Result(*wire.decode(raw), self.spec)

    def submit(self, action_type, actions, dt=None, **options):
        rows = np.asarray(actions, dtype=np.float32)
        if rows.ndim == 1:
            rows = rows[None,:]
        meta = dict(type=action_type, dt=1/self.spec["control_hz"] if dt is None else dt, **options)
        parts = {"actions": dict(data=rows)}
        return Result(*wire.decode(self.execute(meta, parts, submit=True)), self.spec)

    def kinematics(self, request):
        return self.robot.kinematics(request)

    def state(self):
        """Unlimited mode's manager access; never routed by the HTTP server."""
        return self.env.tick_record()

    def save(self, path=None):
        path = Path(path or self.output / "trajectory.npz")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as stream:
            np.savez_compressed(stream, actions=np.array(self.actions, dtype=np.float64).reshape(-1,self.robot.action_dim),
                physics_steps=np.array(self.tick_counts,dtype=np.int64), identity=np.array(self.identity), initial=np.array(self.initial))
        return str(path)

    def verdict(self):
        from .evidence import canonical_state
        info = self.env._info()
        write_json(self.output/"final-state.json",canonical_state(self.env))
        return dict(success=bool(self.env.is_solved()), evaluation_status=info["evaluation_status"],
            scoring_eligible=info["goal_evaluation_complete"] and info["evaluation_status"] == "available",
            n_actions=len(self.actions), sim_steps=self.physics_steps, control_steps=self.control_steps,
            sim_time_s=self.env.sensor_frame().sim_time_s, final_sha256=fingerprint(self.env), initial_sha256=self.initial,
            instance_sha256=self.identity, reason=self.reason, resets=self.resets,
            state_normalization="SI numeric measurements rounded to 12 decimal places; unordered contacts sorted",
            final_raw_sha256=digest(canonical_state(self.env)))

    def close(self):
        try:
            self._end_recording()
        finally:
            self.stack.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
