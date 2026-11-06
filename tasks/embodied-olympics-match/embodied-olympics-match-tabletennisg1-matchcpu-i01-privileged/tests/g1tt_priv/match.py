"""Embodied First Exam: the privileged twin of the G1 table-tennis match (tabletennis_g1, revision g1tt-10+core-0.5).

One match of the sport's own in-process runner (core/local.py play(): no HTTP, no wall clock; the platform's opponent
in its own process, each of its replies received at its own step) with seat A played by a program: every control step
the program gets the seat's view (the state and the camera images it would get over HTTP) plus `truth` (the world's
ground truth: the sport's practice_truth(): the ball's position, velocity and spin, both robots' qpos / qvel, the score,
the rally) and returns one joint-level action body, or None. The episode is the core's episode.jsonl, which
`python3 -m core.episode` replays in a fresh process.

    play(policy, level, seed, data=None, call_limit_s=CALL_LIMIT_S, budget_s=BUDGET_S) -> result dict
    policy: an object with act(view) (development: your program in your own process), or Isolated (the formal match)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

SIM = Path(os.environ.get("G1TT_SIM", Path(__file__).resolve().parents[2]))   # the sim tree (core/, sport/)
CALL_LIMIT_S = 0.5           # one program call: an answer later than this is no command at that step
BUDGET_S = 1800.0            # all the program's calls of one match: past this, no command for the rest of it
ENV = {                      # the frozen instance's sim settings (the realtime twin's compose environment)
    "RO_PLUGIN": str(SIM / "sport/plugin.py"), "RO_SPORT": "tabletennis_g1", "RO_FORMAT": "match", "RO_SEATS": "A",
    "RO_FIRST": "A", "RO_SLOWDOWN": "1", "RO_RENDERER": "mujoco", "RCB_ACTION_LEVEL": "low", "RCB_PLAY": "program",
    "RCB_ACT_RULE": "program", "RO_CAMERA_PROCS": "2", "RO_CAMERA_WORKERS": "4", "RO_PNG_LEVEL": "1",
    "MUJOCO_GL": "osmesa", "PYOPENGL_PLATFORM": "osmesa", "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1",
    "LP_NUM_THREADS": "1"}


def setup(level: int, seed: int, data: str | None = None):
    """(sport, cfg, plugin path) of the frozen instance at `level` / `seed` (development: any level 1-4, any seed)."""
    os.environ.update(ENV)
    os.environ.update(RO_LEVEL=str(int(level)), RO_SEED=str(int(seed)), RCB_DATA=str(data or "/tmp/g1tt_priv"))
    os.chdir(SIM)
    if str(SIM) not in sys.path:
        sys.path.insert(0, str(SIM))
    from core import serve, taskspec
    plugin = os.path.abspath(taskspec.setting("RO_PLUGIN"))
    sport = serve.load_plugin(plugin)
    cfg = serve.config_from_env(taskspec.load(), sport.protocol)
    return sport, cfg, plugin


class Seat:
    """Seat A of the in-process match: the view + truth to the program, its answer back, under the time limits."""

    def __init__(self, sport, policy, call_limit_s: float, budget_s: float):
        self.sport, self.policy, self.m = sport, policy, None
        self.limit, self.budget = float(call_limit_s), float(budget_s)
        self.stats = {"calls": 0, "late": 0, "errors": 0, "none": 0, "over_budget": 0, "program_s": 0.0, "max_s": 0.0}

    def act(self, view):
        st = self.stats
        if st["program_s"] >= self.budget:
            st["over_budget"] += 1
            return None
        view = dict(view, truth=self.sport.practice_truth(self.m, "A"))
        t = time.monotonic()
        try:
            body = self.policy.act(view)
            err = None
        except Exception as exc:  # noqa: BLE001  the program's error: no command at this step
            body, err = None, exc
        dt = time.monotonic() - t
        st["calls"] += 1
        st["program_s"] += dt
        st["max_s"] = max(st["max_s"], dt)
        if err is not None or getattr(self.policy, "failed", False):
            st["errors"] += 1
            return None
        if dt > self.limit:
            st["late"] += 1
            return None
        if body is None:
            st["none"] += 1
        return body


MAX_STEPS = 636000           # the twins' match limit: 6360 s of game time (MATCH_TIMEOUT_S at x1), 0.01 s a step


def play(policy, level: int = 4, seed: int = 4, data: str | None = None, call_limit_s: float = CALL_LIMIT_S,
         budget_s: float = BUDGET_S, render: bool = True, max_steps: int = MAX_STEPS) -> dict:
    sport, cfg, plugin = setup(level, seed, data)
    from core import local
    seat = Seat(sport, policy, call_limit_s, budget_s)
    build = sport.build

    def build_and_keep(c):
        seat.m = build(c)
        return seat.m
    sport.build = build_and_keep
    t0 = time.monotonic()
    try:
        res = local.play(sport, cfg, {"A": seat}, data=data, render=render, plugin=plugin, every=1,
                         max_steps=int(max_steps))
    finally:
        sport.build = build
    res["program"] = dict(seat.stats, program_s=round(seat.stats["program_s"], 3), max_s=round(seat.stats["max_s"], 4),
                          call_limit_s=call_limit_s, budget_s=budget_s)
    res["wall_s"] = round(time.monotonic() - t0, 1)
    res["instance"] = {"level": int(level), "seed": int(seed)}
    if data is not None:
        (Path(data) / "local_result.json").write_text(json.dumps(res, default=float))
    return res


def load_program(policy_dir: str):
    """make_policy(config) of <policy_dir>/program.py (its folder importable)."""
    import importlib.util
    d = os.path.abspath(policy_dir)
    sys.path.insert(0, d)
    spec = importlib.util.spec_from_file_location("program", os.path.join(d, "program.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def public_spec(level: int = 4, seed: int = 4) -> dict:
    """The seat's /spec (as the standard twins' `game spec`; the protocol's timing part aside)."""
    sport, cfg, plugin = setup(level, seed)
    from core import local
    return local.seat_spec(sport, cfg, "A", plugin=plugin)


def main(argv):
    """python3 -m tools.g1tt_priv.match POLICY_DIR [LEVEL [SEED [DATA]]]: one development match of your program in this
    process (the formal match runs it in a process of its own as another user, with the same view and limits)."""
    pdir = argv[0]
    level = int(argv[1]) if len(argv) > 1 else 4
    seed = int(argv[2]) if len(argv) > 2 else 4
    data = argv[3] if len(argv) > 3 else "/tmp/g1tt_priv"
    mod = load_program(pdir)
    pol = mod.make_policy({"spec": public_spec(level, seed), "seat": "A", "level": level, "seed": seed})
    res = play(pol, level, seed, data)
    print(json.dumps({k: res.get(k) for k in ("scores", "winner", "finished", "k", "program", "wall_s")}, default=float))


if __name__ == "__main__":
    main(sys.argv[1:])
