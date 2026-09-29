"""Pure policy input projection: approved sensors, never raw Task/controller info."""
from collections.abc import Mapping
from dataclasses import dataclass
import numpy as np

from topogym.utils.snapshots import freeze

STATE_FIELDS = ("episode_id", "branch_id", "state_id", "physics_step", "sim_time_s")
CALIBRATION_FIELDS = ("resolution_px", "K_px", "distortion", "camera_cv_axes",
                      "T_world_from_camera_cv", "T_camera_cv_from_world")


@dataclass(frozen=True)
class ObservationProfile:
    mode: str
    rgb_camera_ids: tuple
    calibration_camera_ids: tuple
    state_fields: tuple
    robot_fields: Mapping
    calibration: Mapping
    observation_spec: Mapping

    def identity(self):
        return freeze(dict(schema_version=2, mode=self.mode, rgb_camera_ids=self.rgb_camera_ids,
            calibration_camera_ids=self.calibration_camera_ids, state_fields=self.state_fields,
            observation_spec=self.observation_spec,
            calibration=self.calibration))


def _names(value):
    if not isinstance(value, (list, tuple)) or any(not isinstance(x, str) for x in value):
        raise ValueError("Observation field lists must contain names")
    if len(set(value)) != len(value):
        raise ValueError("Duplicate observation field")
    return tuple(value)


def validate_profile(*, mode, settings, camera_specs, action_spec, state_fields,
                     privileged_enabled, raw_observation, proprioception):
    if mode not in {"limited", "unlimited"}:
        raise ValueError("mode must be limited or unlimited")
    if mode == "unlimited" and not privileged_enabled:
        raise PermissionError("Privileged access is disabled")
    settings = {} if settings is None else settings
    if not isinstance(settings, Mapping) or set(settings) - {
        "rgb_camera_ids", "calibration_camera_ids"}:
        raise ValueError("Unknown observation profile setting")
    rgb = _names(settings.get("rgb_camera_ids", tuple(raw_observation["rgb"])))
    calibration_ids = _names(settings.get("calibration_camera_ids", ()))
    extra = tuple(sorted(_names(state_fields)))
    if set(extra) - {"robot", "world", "task"}:
        raise ValueError("Unsupported privileged state field")
    if mode == "limited" and extra:
        raise PermissionError("limited does not allow privileged state fields")
    if not set(rgb) <= raw_observation["rgb"].keys() or not set(calibration_ids) <= set(rgb):
        raise ValueError("Unknown or unpublished camera")
    calibration = {}
    for name in calibration_ids:
        # v1 explicitly publishes fixed calibration only, in either mode.
        spec = camera_specs.get(name, {})
        if spec.get("motion") != "fixed":
            raise ValueError("Only explicitly fixed cameras can publish calibration")
        calibration[name] = {k: spec[k] for k in CALIBRATION_FIELDS}
    robot_fields, robot_spec = {}, {}
    for arm, group in action_spec["groups"].items():
        finger = "finger_position_" + ("m" if group["gripper_field"].endswith("_m") else "rad")
        fields = dict(joint_position_rad=[len(group["arm_joint_names"])],
                      tcp_position_world_m=[3], tcp_orientation_wxyz=[4])
        measured = proprioception["robot"][arm]
        # Preserve the declared robot's actual finger count; do not invent width.
        fingers = np.asarray(measured[finger])
        if fingers.ndim != 1 or not fingers.size:
            raise ValueError("Missing gripper measurements")
        fields[finger] = list(fingers.shape)
        robot_fields[arm] = fields
        robot_spec[arm] = dict(fields=fields, arm_joint_names=group["arm_joint_names"],
                              coordinate_frame="world", orientation="unit wxyz")
    spec = dict(robot=robot_spec, rgb={name: dict(shape=list(raw_observation["rgb"][name].shape),
        dtype="uint8") for name in rgb}, calibration_camera_ids=calibration_ids,
        state_fields=STATE_FIELDS, privileged_fields=extra,
        execution_state="control step receipts; no reward")
    profile = ObservationProfile(mode, rgb, calibration_ids, extra,
                                 freeze(robot_fields), freeze(calibration), freeze(spec))
    # Fail before a segment or policy is initialized if required sensors are absent.
    project_observation(raw_observation, proprioception, profile=profile,
                        execution_state={}, privileged_values={name: {} for name in extra})
    return profile


def build_context(profile, action_spec, timing_spec):
    return freeze(dict(schema_version=2, mode=profile.mode, action_spec=action_spec,
                       timing_spec=timing_spec, observation_spec=profile.observation_spec,
                       observation_profile=profile.identity(), rgb_available=bool(profile.rgb_camera_ids)))


def resolve_profile(env, *, mode="limited", settings=None, state_fields=()):
    """Resolve one profile before initial recording or policy execution."""
    from topogym.config.scene import load_scene_config
    from topogym.sensors.camera_info import camera_contract
    access = env.interaction(privileged=mode == "unlimited")
    cameras = camera_contract(getattr(load_scene_config(env.config).env, "cameras", {}))
    for name, camera in env._world.cameras.items():
        if getattr(camera, "_attached_link", None) is not None or getattr(camera, "_followed_entity", None) is not None:
            cameras[name]["motion"] = "moving"
    return validate_profile(mode=mode,
        settings=settings,
        camera_specs=cameras, action_spec=access.action_spec, state_fields=state_fields,
        privileged_enabled=env.config.enable_privileged, raw_observation=access.observe(),
        proprioception=env._sensors.proprioception())


def project_robot(measurements, robot_fields):
    robot = {}
    for arm, fields in robot_fields.items():
        robot[arm] = {}
        for name, shape in fields.items():
            value = np.asarray(measurements[arm][name])
            if list(value.shape) != list(shape) or value.dtype.kind not in "fiu" or not np.isfinite(value).all():
                raise ValueError("Invalid proprioception measurement")
            robot[arm][name] = value
    return robot


def project_observation(raw_observation, proprioception, *, profile,
                        execution_state, privileged_values):
    state = {key: raw_observation["state"][key] for key in STATE_FIELDS}
    if any(proprioception["state"][key] != state[key] for key in STATE_FIELDS):
        raise ValueError("Proprioception and RGB do not share a state")
    robot = project_robot(proprioception["robot"], profile.robot_fields)
    rgb = {}
    for name in profile.rgb_camera_ids:
        value = np.asarray(raw_observation["rgb"][name])
        if value.dtype != np.uint8 or list(value.shape) != list(profile.observation_spec["rgb"][name]["shape"]):
            raise ValueError("RGB shape or type changed")
        rgb[name] = value
    for name, calibration in profile.calibration.items():
        actual = raw_observation["cameras"][name]
        for key in ("K_px", "T_world_from_camera_cv", "T_camera_cv_from_world"):
            if not np.allclose(actual[key], calibration[key], atol=1e-7, rtol=0):
                raise ValueError("Published fixed camera calibration changed")
    result = dict(rgb=rgb, robot=robot,
                  state=state, execution_state=execution_state)
    if profile.calibration_camera_ids:
        result["camera_calibration"] = profile.calibration
    if profile.mode == "unlimited":
        result["privileged"] = {name: privileged_values[name] for name in profile.state_fields}
    return freeze(result)
