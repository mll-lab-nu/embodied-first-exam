"""HumanCLAW privileged-mode tools: the simulator itself, with the episode's privileged state, free resets, and replay.

    from hc_tools import Env
    env = Env()                         # the frozen episode (/app/instance.json), on the GPU; ~30 s to build
    out = env.step(0, 0.4)              # one action [action_id, value] (see ACTIONS); returns the new state
    env.state()                         # body position / heading, actions used, done, success, distance to target
    env.targets()                       # the target category, every target object's centre and bounding box
    env.shortest_path([x, y, z], agent_radius=0.35)   # navmesh path from the body to a point (radius: a wider body)
    env.rgb()                           # the head camera's image (H x W x 3 uint8)
    env.reset()                         # back to the frozen start (a fresh simulator), any number of times
    env.save("/app/output/trajectory.npz")   # this episode's actions so far: the deliverable

    python /opt/tools/hc_tools.py actions                    # the action table
    python /opt/tools/hc_tools.py replay /app/output/trajectory.npz [--video out.mp4] [--json out.json]

Coordinates are Habitat's world frame: y up, metres; heading_deg is the body's facing about +y (0 = facing -z, + =
turning left). A replay of the same actions from the frozen start reproduces the same episode on the same GPU model
(the motion model's noise is seeded at every reset; another GPU model computes it slightly differently, and the
physics amplifies that), which is what the verifier checks on this machine: it replays the trajectory twice, each
time in a fresh process from its own copy of the instance, and both must succeed and end in the same state.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hc_core  # noqa: E402

DEFAULT_INSTANCE = os.environ.get("HC_INSTANCE", "/app/instance.json")
TRAJ_FORMAT = "npz with `actions`: float array (T, 2), rows [action_id, value], 1 <= T <= max_steps"


class Env:
    def __init__(self, instance: str = DEFAULT_INSTANCE, device: str | None = None):
        self.session = hc_core.Session(instance, device=device)
        self.inst = self.session.inst

    # -- the episode --
    def reset(self) -> dict:
        self.session.reset()
        return self.state()

    def step(self, action_id: float, value: float = 0.0) -> dict:
        row, notes = hc_core.clip_row([action_id, value])
        self.session.act(row)
        return {**self.state(), "clamped": notes}

    def run(self, actions) -> dict:
        """Run several actions in order (stops at the episode's end)."""
        for a in np.asarray(actions, dtype=np.float64).reshape(-1, 2):
            if self.session.done:
                break
            self.step(*a)
        return self.state()

    def save(self, path: str = "/app/output/trajectory.npz") -> str:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        np.savez(path, actions=np.asarray(self.session.rows, dtype=np.float64).reshape(-1, 2))
        return path

    # -- what the body sees --
    def rgb(self) -> np.ndarray:
        return self.session.ego_rgb()

    # -- privileged state --
    def state(self) -> dict:
        s = self.session
        a = s.env.agent
        p, q = a.translation, a.rotation
        fwd = q.transform_vector(hc_core_vec3(s, 0.0, 0.0, 1.0))   # the SMPL-X body faces its local +z
        geo = s.env.metric_target_geometry()
        r = s.result or {}
        return {"position": [float(p.x), float(p.y), float(p.z)],
                "heading_deg": math.degrees(math.atan2(-float(fwd.x), -float(fwd.z))),
                "pelvis_rise_m": s.pelvis_rise(), "actions_used": s.n_actions, "actions_left": s.max_steps - s.n_actions,
                "done": s.done, "success": bool(r.get("success", False)),
                "body_target_distance_m": float(geo["body_target_aabb_distance_m"]),
                "sits_so_far": int(s.metrics.n_sit),
                "pelvis_touches_target": bool(s.metrics._last_motion_pelvis_target_contact)}

    def targets(self) -> dict:
        s = self.session
        geo = s.env.metric_target_geometry()
        return {"category": s.episode.object_category, "interaction": bool(s.env.is_interact_episode()),
                "rule": ("stop after sitting, with the pelvis touching the target at the end of the last motion"
                         if s.env.is_interact_episode() else
                         "stop with the body within 0.2 m of the nearest target's bounding box"),
                "objects": [{"center": o.get("center")} for o in s.episode.goal_objects],
                "aabbs": [{"min": list(lo), "max": list(hi)} for lo, hi in s.env._target_aabbs()],
                "geometry_now": {k: v for k, v in geo.items() if isinstance(v, (int, float, str, bool, list))},
                "goal_viewpoints": s.episode.viewpoint_positions}

    def shortest_path(self, goal, start=None, agent_radius: float | None = None) -> dict:
        """Habitat's navmesh path (geodesic distance, waypoints) from the body (or `start`) to `goal`. The scene's own
        navmesh by default; `agent_radius` (m) builds (once, cached) a navmesh for a wider body, whose paths keep that
        far from walls and furniture (the human body is wider than the default)."""
        import habitat_sim
        sim = self.session.env.sim
        pf = sim.pathfinder
        if agent_radius is None and not pf.is_loaded:
            agent_radius = 0.25
        if agent_radius is not None:
            cache = self.__dict__.setdefault("_pathfinders", {})
            key = (id(sim), round(float(agent_radius), 3))
            if key not in cache:
                settings = habitat_sim.NavMeshSettings()
                settings.set_defaults()
                settings.agent_radius, settings.agent_height = float(agent_radius), 1.6
                if hasattr(settings, "include_static_objects"):
                    settings.include_static_objects = True
                pf_new = habitat_sim.PathFinder()
                for cell in (settings.cell_size, 0.1, 0.15):   # a large scene can exceed Detour's limits: coarser cells
                    settings.cell_size = cell
                    if sim.recompute_navmesh(pf_new, settings) and pf_new.is_loaded:
                        break
                else:
                    raise RuntimeError(f"could not build a navmesh for agent_radius={agent_radius}")
                cache[key] = pf_new
            pf = cache[key]
        a = self.session.env.agent.translation
        # from the body: its pelvis is ~0.9 m above the floor, too high for the navmesh snap on some floors
        st = np.asarray(start if start is not None else [a.x, a.y - 0.9, a.z], dtype=np.float32)
        st = pf.snap_point(st)
        path = habitat_sim.ShortestPath()
        path.requested_start, path.requested_end = st, pf.snap_point(np.asarray(goal, dtype=np.float32))
        found = pf.find_path(path)
        return {"found": bool(found), "geodesic_m": float(path.geodesic_distance),
                "points": [[float(v) for v in p] for p in path.points]}

    def state_sha(self) -> str:
        return self.session.state_sha()

    def video(self, path: str) -> str:
        hc_core.episode_video(self.session, path)
        return path

    def close(self) -> None:
        self.session.close()


def hc_core_vec3(s, x, y, z):
    import magnum as mn
    return mn.Vector3(x, y, z)


# ------------------------------------------------------------------------------------------------ trajectory files
def load_actions(path: str, max_steps: int) -> np.ndarray:
    """The deliverable's rows, validated (raises ValueError with the reason)."""
    with np.load(path, allow_pickle=False) as d:
        if "actions" not in d.files:
            raise ValueError(f"no `actions` entry ({TRAJ_FORMAT})")
        a = np.asarray(d["actions"])
    if a.dtype.kind not in "fiu" or a.ndim != 2 or a.shape[1] != 2 or not 1 <= len(a) <= max_steps:
        raise ValueError(f"`actions` is {a.dtype} {list(a.shape)}; expected {TRAJ_FORMAT}")
    a = a.astype(np.float64)
    for i, row in enumerate(a):
        try:
            hc_core.clip_row(row)
        except hc_core.BadAction as exc:
            raise ValueError(f"row {i}: {exc}") from None
    return a


def replay(instance: str, traj: str, *, video: str | None = None, device: str | None = None) -> dict:
    """A fresh Session from the frozen instance, the trajectory's actions in order, HumanCLAW's verdict."""
    t0 = time.time()
    s = hc_core.Session(instance, device=device)
    start_sha = s.state_sha()
    actions = load_actions(traj, s.max_steps)
    used = 0
    for row in actions:
        if s.done:
            break
        s.act(row)
        used += 1
    r = s.result or {}
    m = (r.get("metrics") or {}).get("success") or {}
    out = {"success": bool(r.get("success", False)), "ended": bool(s.done), "rule": r.get("rule"),
           "n_rows": int(len(actions)), "n_executed": used, "n_ignored": int(len(actions) - used),
           "start_sha": start_sha, "final_sha": s.state_sha(),
           "final_body_target_aabb_distance_m": m.get("final_body_target_aabb_distance_m"),
           "active_stop": m.get("active_stop"), "n_sit": m.get("n_sit"), "seconds": round(time.time() - t0, 1)}
    if video:
        try:
            hc_core.episode_video(s, video)
            out["video"] = True
        except Exception as exc:  # noqa: BLE001 -- a video never decides anything
            out["video"] = False
            out["video_error"] = repr(exc)[:300]
    s.close()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("actions")
    r = sub.add_parser("replay")
    r.add_argument("traj")
    r.add_argument("--instance", default=DEFAULT_INSTANCE)
    r.add_argument("--video")
    r.add_argument("--json")
    r.add_argument("--device")
    a = ap.parse_args(argv)
    if a.cmd == "actions":
        print(hc_core.__doc__.split("An action is a row")[1].split("Success (")[0].strip())
        return 0
    out = replay(a.instance, a.traj, video=a.video, device=a.device)
    s = json.dumps(out, indent=1)
    if a.json:
        open(a.json, "w").write(s + "\n")
    print(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
