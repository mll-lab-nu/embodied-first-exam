"""Episode-bound operator access: no reset, make, close or seed mutation."""
import weakref
from topogym.utils.snapshots import freeze


def public_info(info):
    keys = ("episode_id", "state_ref", "state_id", "branch_id", "control_step",
            "physics_step", "sim_time_s", "physics_steps", "action_duration_s",
            "restored_from_state_id", "goal_evaluation_complete", "terminal_revision", "task_terminated")
    result = {key: info[key] for key in keys if key in info}
    complete = bool(info.get("goal_evaluation_complete", False))
    status = info.get("evaluation_status", "available" if complete else "unavailable")
    if status not in {"available", "unavailable"}:
        raise ValueError("Invalid public evaluation status")
    if info.get("task_terminated") is True:
        status = "available"
    result["evaluation_status"] = status
    result["task_success"] = bool(info.get("task_success")) if status == "available" else None
    result["task_outcome"] = ("success" if info.get("task_success") else "failure") if info.get("task_terminated") is True else (
        "ongoing" if status == "available" else "unknown")
    code = info.get("failure_code")
    if info.get("task_terminated") is True and not info.get("task_success") and code in {"wire_touched", "task_failed"}:
        result["failure_code"] = code
    reason = info.get("termination_reason")
    result["termination_reason"] = (
        None if reason is None else "time_limit" if reason == "time_limit" else "task_terminal")
    return freeze(result)


class Interaction:
    __slots__ = ("__owner", "__episode_id", "__privileged")

    def __init__(self, env, *, privileged=False):
        self.__owner = weakref.ref(env)
        self.__episode_id = env._episode_id
        self.__privileged = env.privileged if privileged else None

    def _env(self):
        env = self.__owner()
        if env is None or env._closed or env._episode_id != self.__episode_id:
            raise RuntimeError("Interaction handle expired; the owner must grant a new episode handle")
        return env

    @property
    def action_spec(self):
        return self._env().action_spec

    @property
    def observation_spec(self):
        return self._env().observation_spec

    @property
    def timing_spec(self):
        return self._env().timing_spec

    def step(self, action):
        env = self._env()
        try:
            observation, reward, terminated, truncated, info = env.step(action)
        except Exception:
            if env._faulted:
                raise RuntimeError("Environment execution failed; consult owner evidence") from None
            raise
        return observation, reward, terminated, truncated, public_info(info)

    def observe(self):
        return self._env().observe()

    def render(self):
        return self._env().render()

    def is_solved(self):
        return self._env().is_solved()

    def rewind_to(self, state_ref):
        self._env()
        if self.__privileged is None:
            raise PermissionError("Rewind requires privileged interaction")
        observation, info = self.__privileged.rewind_to(state_ref)
        return observation, public_info(info)

    def get(self, name):
        self._env()
        if self.__privileged is None:
            raise PermissionError("Detailed state requires privileged interaction")
        return self.__privileged.get(name)
