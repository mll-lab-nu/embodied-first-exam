"""TaskSpec and the environment: the ONE place the core reads a task's configuration and its process environment from
(core 0.4.0; tools/ci/check-core-env.py: no other core module touches os.environ).

The generator (tools/generate.py) writes the task's TaskSpec to tasks/<id>/environment/sim/taskspec.json (the same file
as tests/taskspec.json; task.toml [metadata.taskspec] records its id, sha256 and options). The sim service's /srv is
that sim directory, so the default path is `taskspec.json` next to this package (the directory above core/);
RO_TASKSPEC names another file. Two schemas are read:

  "ro-taskspec/1" (gen-1)   {"schema", "id", "variant_of", "arm", "sport", "revision", "core", "generator", "track",
                             "format", "seats", "sides", "level", "protocol", "resource", "seed_cell",
                             "timing": {"prepare_s", "review_s", "match_s", "clock_s"},
                             "options": {OPTION: value, ...}, "practice": {...}}
  "eo-taskspec/1" (fwspec)  olympiad_review/handoff/fwspec/taskspec.schema.yaml: slots, timing (control_dt_s, slowdown,
                             start_barrier, prepare_s, wall_cap_s, grace_s, clock_s), termination, action
                             (layer_delay_steps L, in_flight_per_robot K, limits, batch, safe_action; core 0.5.0:
                             reaction_delay_steps is refused), sensors, review, practice, ... (read_eo maps it
                             onto the same TaskSpec)

Options (OPTIONS below; the generator applies --variant > the task entry's options > sport.toml [options] > DEFAULTS):

    practice.package   api | open                     the seat's practice package (the generator, the practice service)
    practice.access    throughout | preparation | preparation_review   when the platform's practice service is open
    timing.slowdown    a positive number               the wall length of a control step = dt x slowdown; the ONE path
                                                       to the match's slowdown (match_config -> MatchConfig.slowdown)
    timing.t0          barrier | service_start         barrier: the preparation counts from the start barrier t0
                                                       (core/phases.py, POST /<seat>/session); service_start: from
                                                       the service start (tools that start no Harbor trial)
    timing.match_cap   void                            the wall-clock cap is a platform safety cut-off: hitting it voids
    review.source      shell | seat                   shell (the default; the lead's decision 10-21, rule 3: a review
                                                       is written by the model itself): a model seat's review only
                                                       from the agent's own tool call (core/reviews.py);
                                                       seat: a research variant, any process of the seat (core 0.4.0's
                                                       default before 10-21; core/sources.py)
    final_program      optional | required | post_match   post_match (the default, decided 10-24): after the final
                                                       whistle the world's replies carry the TaskSpec's post-match
                                                       request (deliverables.post_match: write controller.toml for
                                                       the last fielded program; never scored); optional: no request;
                                                       required: the instructions ask for /app/output/final/run.sh
    act.limits         derived | {"rate_per_s", "open_requests"}    the HTTP limits per seat (core/acts.py)
    api.outage_rule    unrecovered_or_cap              the verifier's rule for model-API failures

The environment (ENV below: one table). Every environment name a core module uses is declared there with its kind, and
setting(name) is its only reader (an undeclared name is a KeyError, so a new name cannot slip in unseen):

    override   a TaskSpec value a runtime tool may still change: the ALLOWED OVERRIDES (OPTION_ENV, TIMING_ENV,
               MATCH_ENV, TEAM_CHANNEL_ENV, SENSOR_ENV). A value that differs from taskspec.json (and matters to the file's
               protocol) is recorded in TaskSpec.overrides, every time; final.json carries it and the verifier then
               sets official_config = 0, so an experiment never mixes with official results
    fixture    the Run's binding of this match (seed, first, the seed's salt and index, seat -> player mode, opponent
               codes, ids): never a task option, never an override
    deploy     where and how the service runs (paths, ports, seat hosts, worker CPUs, post-match jobs): never play
    seat       the seat's own client (core/client.py, core/game.py in the seat: ro_taskspec.py next to ro_client.py)
    practice   the practice service and the seat's sandbox (core/practice.py, core/sandbox.py)

Without a file (unit tests, in-process tools, older tasks) there is nothing to differ from: `id` and `sha256` are None,
`overrides` is {}, every value is the environment's or the default, and one default keeps the earlier behaviour:
timing.t0 = service_start (no start barrier); review.source is the rule's (shell) unless RO_READY_FROM_SHELL=0.

A service calls load() once when it starts and keeps the result. The file is parsed once per process (cached by path).
This module needs the standard library only: the generator copies it into every seat as ro_taskspec.py.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA = "ro-taskspec/1"
SCHEMA_EO = "eo-taskspec/1"
SCHEMAS = (SCHEMA, SCHEMA_EO)
ROOT = Path(__file__).resolve().parent

DEFAULTS: dict = {
    "practice.package": "api",
    "practice.access": "throughout",
    "timing.slowdown": None,                 # None: the sport's [timing] slowdown (the generator fills it in)
    "timing.t0": "barrier",
    "timing.match_cap": "void",
    "review.source": "shell",                # the lead 10-21 (rule 3): only the agent's own tool call (core/reviews.py)
    "final_program": "post_match",           # 10-24: the post-match controller.toml request (never scored)
    "act.limits": "derived",
    "api.outage_rule": "unrecovered_or_cap",
}
CHOICES: dict = {
    "practice.package": ("api", "open"),
    "practice.access": ("throughout", "preparation", "preparation_review"),
    "timing.t0": ("barrier", "service_start"),
    "timing.match_cap": ("void",),
    "review.source": ("shell", "seat"),
    "final_program": ("optional", "required", "post_match"),
    "api.outage_rule": ("unrecovered_or_cap",),
}
OPTIONS = tuple(DEFAULTS)
LEGACY_VALUES = {("practice.package", "interface"): "api"}      # the generator's old name of the api package

# timing (seconds; None = not set / no limit). ro-taskspec/1 files have prepare_s, review_s, match_s, clock_s;
# eo-taskspec/1 files also the start barrier (barrier_lead_s, t0_wait_s), wall_cap_s and grace_s.
TIMING_DEFAULTS: dict = {
    "prepare_s": None,       # None: the protocol's fallback (realtime: review_s; turn: 1800), as before core 0.3.0
    "review_s": 60.0,        # READY_TIMEOUT_S: a review's window from the freeze (eo-taskspec/1: review.window_s)
    "match_s": None,         # MATCH_TIMEOUT_S: the wall cap counted from the match start (None: no limit)
    "wall_cap_s": None,      # eo-taskspec/1 timing.wall_cap_s: the platform safety cut-off counted from t0
    "clock_s": 3600.0,       # CLOCK_S: a turn-based seat's chess clock
    "barrier_lead_s": 0.2,   # BARRIER_LEAD_S: the lead between the last ready and the run
    "t0_wait_s": 600.0,      # T0_WAIT_S: the start barrier opens this long after the first arrival at the latest
    "grace_s": None,         # eo-taskspec/1 timing.grace_s: the seat containers' grace after the end (the Backend's)
}

# ------------------------------------------------------------------------------------------- the allowed overrides
# environment -> option (legacy names first)
OPTION_ENV: dict = {
    "timing.slowdown": ("RO_SLOWDOWN", "RCB_SLOWDOWN"),
    "practice.access": ("DEVWORLD_ACCESS",),
    "review.source": ("RO_READY_FROM_SHELL",),
    "timing.t0": ("RO_T0",),
    "final_program": ("RO_FINAL_PROGRAM",),
    "act.limits": ("RO_ACT_LIMITS",),
}
# environment -> timing key (the first name that is set wins)
TIMING_ENV: dict = {
    "prepare_s": ("PREPARE_TIMEOUT_S", "START_TIMEOUT_S"),
    "review_s": ("READY_TIMEOUT_S",),
    "match_s": ("MATCH_TIMEOUT_S",),
    "wall_cap_s": ("RO_WALL_CAP_S",),
    "clock_s": ("CLOCK_S",),
    "barrier_lead_s": ("BARRIER_LEAD_S",),
    "t0_wait_s": ("T0_WAIT_S",),
}
# environment -> the match configuration's task part (TaskSpec.match; match_config builds the MatchConfig from it). A
# value is an override where the file states it (an ro-taskspec/1 file's level only when it is not null: a task that
# leaves the level to the run)
MATCH_ENV: dict = {
    "sport": "RO_SPORT", "format": "RO_FORMAT", "seats": "RO_SEATS", "sides": "RO_SIDES", "level": "RO_LEVEL",
    "action_level": "RCB_ACTION_LEVEL", "play": "RCB_PLAY", "params": "RO_PARAMS", "renderer": "RO_RENDERER",
}
TEAM_CHANNEL_ENV = "RO_TEAM_CHANNEL"          # on | off: a declared team channel switched off (an experiment)
# the cameras' delivery latency in control steps (eo-taskspec/1 sensors.cameras[].latency_steps; a gen-1 task: the
# sport's sport.toml [observation] latency_steps): an experiment's other value (core 0.4.0, the observation pipeline)
SENSOR_ENV: dict = {"camera_latency_steps": "RO_CAMERA_LATENCY_STEPS"}
LEGACY_ENV = {**{n: f"options.{k}" for k, ns in OPTION_ENV.items() for n in ns},
              **{n: f"timing.{k}" for k, ns in TIMING_ENV.items() for n in ns},
              **{n: f"match.{k}" for k, n in MATCH_ENV.items()}, TEAM_CHANNEL_ENV: "team_channel",
              **{n: f"sensors.{k}" for k, n in SENSOR_ENV.items()}}
# deployment settings carried on the TaskSpec (no task option)
RUNTIME_ENV: dict = {"act_rule": ("RCB_ACT_RULE", "per_response"), "devgate": ("RO_DEVWORLD_GATE", None)}
# what each protocol reads: an environment value outside it is not an override (e.g. CLOCK_S in a realtime task)
RELEVANT: dict = {
    "realtime": {"timing.prepare_s", "timing.review_s", "timing.match_s", "timing.wall_cap_s",
                 "timing.barrier_lead_s", "timing.t0_wait_s", *(f"options.{k}" for k in OPTIONS),
                 *(f"match.{k}" for k in MATCH_ENV), "team_channel", *(f"sensors.{k}" for k in SENSOR_ENV)},
    "turn": {"timing.prepare_s", "timing.match_s", "timing.wall_cap_s", "timing.clock_s", "timing.t0_wait_s",
             *(f"options.{k}" for k in OPTIONS if k != "timing.slowdown"), *(f"match.{k}" for k in MATCH_ENV),
             "team_channel"},
}
REQUEST_LIMIT_KEYS = ("rate_per_s", "open_requests")
TRACKS = ("athlete", "engineer")                        # the track is the task's explicit declaration, never inferred
LAYERS = {"skill": "high", "joint": "low", "high": "high", "low": "low"}   # action layer -> the legacy action level


# Values the framework has not decided yet (olympiad_review/handoff/fwspec_decisions_1020.md): the Host's defaults in
# ONE place; the code reads them from here only (change them here, nowhere else)
UNDECIDED: dict = {
    "layer_delay_steps": 0,            # #3: the planning budget L of a task that declares none
    "in_flight_extra": 1,              # K = L + in_flight_extra when a task declares none (eo-seat/1 9.3; to verify)
    "resign": "any_seat",              # #13: any seat of a side resigns for it (all_seats: every seat of the side must)
    "wall_cap_from": {"eo-taskspec/1": "t0", "ro-taskspec/1": "match_start"},   # #1: where the safety cut-off counts from
    "turn_review_window_s": 300.0,     # a turn task's per-move review window when it declares none (gen-2 writes
                                       # review.window_s = 0: "on the chess clock"); eo-seat/1 9.7: it never forfeits
}


# ------------------------------------------------------------------------------------------- the environment table
@dataclass(frozen=True)
class Var:
    kind: str                   # override | fixture | deploy | seat | practice
    default: str | None
    doc: str


KINDS = ("override", "fixture", "deploy", "seat", "practice")
ENV: dict = {
    # the allowed overrides (tables above)
    **{n: Var("override", None, f"TaskSpec {k}") for n, k in LEGACY_ENV.items()},
    "RO_TASKSPEC": Var("deploy", None, "the TaskSpec file (default: taskspec.json next to core/)"),
    "RCB_ACT_RULE": Var("deploy", "per_response", "per_response | program: the metering's decision rule"),
    "RO_DEVWORLD_GATE": Var("deploy", None, "the practice gate file the sim writes (devworld access)"),
    # the Run's binding of this match (the Fixture, resolved by the Runner)
    "RO_SEED": Var("fixture", "1", "the match seed (a hidden official seed: with RO_SEED_SALT)"),
    "RO_SEED_SALT": Var("fixture", "", "a hidden official seed's salt (core/seeds.py; the sim only)"),
    "RO_SEED_INDEX": Var("fixture", "", "the hidden seed's index in its cell (information)"),
    "RO_FIRST": Var("fixture", None, "the side that starts"),
    "RCB_PLAYER_MODE": Var("fixture", "model", "every seat's player mode (model | oracle | builtin)"),
    "RO_FIXTURE": Var("fixture", None, "an eo-fixture/1 file: fixture_id, codes (opponent pseudonyms), continuity"),
    "RO_CONTINUITY": Var("fixture", None, "the Runner's continuity of the Run (JSON {mode, seats: {seat: {position, "
                                          "of, carried}}, quota}); a fixture file (RO_FIXTURE) wins"),
    "RO_SEAT_CODES": Var("fixture", "", "SEAT=Opponent-N,...: the entrants' pseudonyms without a fixture file"),
    "RO_RUN_ID": Var("fixture", None, "the Run id (eo-run/1 run_id) for the records"),
    "RO_DRAWS": Var("fixture", "", "1: the fixture allows a draw (eo-fixture/1 draws, core 0.5.2: a round-robin "
                                   "fixture of a sport with a draw point); empty: every match is decided"),
    # deployment: paths, ports, hosts, post-match jobs
    "RO_PLUGIN": Var("deploy", None, "the sport's plugin.py"),
    "RCB_DATA": Var("deploy", "/data", "the match's data directory"),
    "RCB_PORT": Var("deploy", "8000", "the match service's port"),
    "SEAT_HOSTS": Var("deploy", "", "SEAT=host,...: the containers each seat's requests must come from"),
    "RO_METER_PROXY": Var("deploy", "metering/think_proxy.py", "the metering proxy (relative to the sim directory)"),
    "RO_REPLAY_TIMEOUT_S": Var("deploy", "600", "the fresh-process replay's timeout"),
    "RCB_RENDER_VIDEO": Var("deploy", "0", "1: the spectators' replay video after the match"),
    "RCB_VIDEO_TIMEOUT_S": Var("deploy", "300", "the replay video's timeout"),
    "RCB_BROADCAST": Var("deploy", "1", "1: the spectators' broadcast log"),
    "RO_VIDEO_SCENE": Var("deploy", "presentation", "presentation | match: the spectators' scene"),
    "RO_VIDEO_RENDERER": Var("deploy", None, "the spectators' renderer"),
    "RO_SESSION_EVENTS": Var("deploy", None, "the Backend's session events file (JSON lines: harness exits)"),
    "RO_ABORT_FILE": Var("deploy", None, "why the platform stops a match (SIGUSR2): {reason, where}"),
    "RO_CAMERA_PROCS": Var("deploy", "1", "render processes per seat's camera worker: a job's tiles drawn side by "
                           "side (core/observe.TilePool; sport.toml [observation] render_procs)"),
    "RO_CAMERA_WORKERS": Var("deploy", "1", "the every-step camera (core/stream.py): frames of a seat drawn at once, "
                             "each in its own camera worker (sport.toml [observation] render_workers)"),
    "MUJOCO_GL": Var("deploy", "osmesa", "MuJoCo's OpenGL backend of this process (osmesa: CPU, egl: GPU); core 0.5.5: "
                     "checked against the task's sensors.render_backend"),
    "RO_RENDER_BACKEND_OVERRIDE": Var("deploy", "", "core 0.5.5: 1 = draw the players' images with another backend "
                                      "than the task declares (an experiment: recorded as an override, never official)"),
    "RO_WORLD_CPU": Var("deploy", "", "core 0.5.5: the world thread's own CPU: 'first' (the lowest CPU of the "
                        "process's affinity) or a CPU number; the worker processes (camera, render, plan) without "
                        "their own RO_<KIND>_<SEAT>_CPUS then leave it free (sport.toml [observation] world_cpu)"),
    "RO_HOST_CPUS": Var("deploy", "1", "core 0.5.5: with the world thread on its own CPU (RO_WORLD_CPU), how many CPUs "
                        "the world process's other threads get next to it (core/workers.host_cpus)"),
    "RO_CPUS_ALL": Var("deploy", "", "core 0.5.5: the world container's CPUs (set by the world process for the "
                       "processes it starts: core/workers.pin_host_threads; their own affinity may be narrower)"),
    "RO_PLATFORM_CPUS": Var("deploy", "", "core 0.5.5: the CPUs of a platform side's own planner process (a scripted "
                            "opponent deciding as a player seat): 'last:N' (the last N of the world container's "
                            "affinity) or a list; the worker processes without their own RO_<KIND>_<SEAT>_CPUS leave "
                            "them free (sport.toml [formats.<f>] platform_cpus)"),
    "RO_PLATFORM_SEAT": Var("deploy", "process", "core 0.5.6: how a platform seat's program runs (core/platform_seat.py): "
                            "process (the rule: its own process on RO_PLATFORM_CPUS) or inline (in the world's process; "
                            "a diagnostic, recorded as an override, never official)"),
    "RO_PLAN_WORKERS": Var("deploy", "1", "core 0.5.6: the plan workers of each seat (the Athlete track's platform "
                           "skill planning, core/workers.plan_workers; sport.toml plan_workers)"),
    "RO_PLAN_CPUS": Var("deploy", "", "core 0.5.6: the CPUs of each seat's plan workers, the same N for every seat, "
                        "exclusive (core/workers.plan_cpus; sport.toml plan_cpus); empty: not pinned apart"),
    "RO_PNG_LEVEL": Var("deploy", "6", "zlib level of the players' PNG images (lossless at any level; sport.toml "
                        "[observation] png_level)"),
    "OMP_NUM_THREADS": Var("deploy", None, "BLAS threads of a worker process (process_default)"),
    # the float mode (core/floatmode.py, core 0.5.1): the Runner sets all three (portable) or none (native); the
    # world records them in its episode header, the replay entry points restart under the recorded ones
    "NPY_DISABLE_CPU_FEATURES": Var("deploy", None, "numpy's SIMD features switched off (float mode portable)"),
    "OPENBLAS_CORETYPE": Var("deploy", None, "the OpenBLAS kernel pinned (float mode portable)"),
    "MKL_CBWR": Var("deploy", None, "MKL's conditional bitwise reproducibility (float mode portable)"),
    "RO_FLOAT_REEXEC": Var("deploy", "", "set by a replay entry point that restarted itself under the episode's "
                                         "float mode (it never restarts twice)"),
    # the seat's client (ro_client, game)
    "SIM_URL": Var("seat", "http://sim:8000", "the match service"),
    "SEAT": Var("seat", "A", "this seat"),
    "PRACTICE_URL": Var("seat", "http://practice:8100", "the practice service"),
    "RO_AGENT_SHELLS": Var("seat", "", "the harness's own process names (players/adapters.toml shell_markers)"),
    "RO_PROGRAM_DIR": Var("seat", "/app/output", "the seat's program files (the deploy record's program sha)"),
    "RO_PROGRAM_NAME": Var("seat", "", "set by `game program` for the program it starts: the program's name"),
    "RO_PROGRAM_LAUNCH": Var("seat", "", "set by `game program` for the program it starts: its launch number"),
    "RO_SESSION_WAIT_S": Var("seat", "900", "ro_client --session: give up after this long"),
    "RO_SESSION_CONNECT_S": Var("seat", "300", "ro_client --session: wait this long for the service to answer"),
    "RO_PLAYER_SEED": Var("seat", "0", "a built-in player's seed (python -m core.client MODULE:FACTORY)"),
    "RO_RULES": Var("seat", "/opt/rules/RULES.md", "the task's full rules (RULES.md) that `game rules` prints"),
    # the practice service and the seat's sandbox
    "PRACTICE_SEAT": Var("practice", None, "the seat the practice service belongs to"),
    "PRACTICE_PORT": Var("practice", "8100", "the practice service's port"),
    "PRACTICE_WORLDS": Var("practice", None, "the most open practice worlds (default sport.toml [devworld])"),
    "PRACTICE_IDLE_S": Var("practice", "1800", "a practice world closes after this long idle"),
    "PRACTICE_START_METHOD": Var("practice", "spawn", "multiprocessing start method of a practice world"),
    "PRACTICE_START_S": Var("practice", "300", "a practice world must start within this long"),
    "PRACTICE_TRUTH": Var("practice", "", "1: ground truth (tasks without a TaskSpec)"),
    "DEVWORLD_GATE": Var("practice", "", "the gate file the sim writes (devworld access)"),
    "DEVWORLD_PROTOCOL": Var("practice", "", "turn: the turn sports' practice rule"),
    "RO_PRACTICE_HOME": Var("practice", None, "the sandbox tree (default: the directory above core/)"),
    "RO_PRACTICE_LOG": Var("practice", "/var/log/ro_practice/usage.jsonl", "the sandbox's usage log"),
    "RO_PLUGIN_REL": Var("practice", "sport/plugin.py", "the sport's plugin.py under the sandbox tree"),
    "RO_SANDBOX_OPPONENTS": Var("practice", "none", "the opponents the seat's sandbox builds"),
    "RO_SERVICE_OPPONENTS": Var("practice", "", "the practice service's opponents (information)"),
    "PRACTICE_OPPONENTS": Var("practice", "", "the practice service's opponents when set (gen-2: what its files build)"),
    "PRACTICE_PLAYER_URL": Var("practice", "", "the practice player's container (core/practice_player.py; empty: no practice player)"),
    "PRACTICE_PLAYER_LOCAL": Var("practice", "", "module:Class of an in-process practice player (tests and checks only)"),
    "PRACTICE_PLAYER_TIMEOUT_S": Var("practice", "10", "the deadline of one call to the practice player"),
}
# names with a seat or a worker kind in them: <SEAT> = a seat id, <KIND> = a worker kind (upper case)
ENV_PATTERNS: dict = {
    "PLAYER_MODE_<SEAT>": Var("fixture", None, "the seat's player mode (model | oracle | builtin)"),
    "RO_PLAYER_CONFIG_<SEAT>": Var("fixture", "", "the seat's player configuration (information)"),
    "RO_<KIND>_<SEAT>_CPUS": Var("deploy", "", "the CPUs a worker process is pinned to (e.g. 4-7,9)"),
}
HIDDEN_ENV = ("RO_SEED_SALT", "RO_SEED_INDEX", "RCB_SEED_SALT", "RCB_SEED", "RO_SEED", "DUEL_SEED")
_PAT = {p: re.compile("^" + re.escape(p).replace("<SEAT>", "[A-Za-z0-9]{1,8}").replace("<KIND>", "[A-Z]{1,16}") + "$")
        for p in ENV_PATTERNS}
_MISSING = object()


def declared(name: str) -> Var:
    """The declaration of an environment name (KeyError: not declared)."""
    if name in ENV:
        return ENV[name]
    for p, rx in _PAT.items():
        if rx.match(name):
            return ENV_PATTERNS[p]
    raise KeyError(f"the core reads no environment variable {name!r} (core/taskspec.py ENV declares the names)")


def _environ(environ):
    return os.environ if environ is None else environ


def setting(name: str, default=_MISSING, environ=None) -> str | None:
    """The environment's value of a declared name (`default`, else the declaration's default, when unset or empty)."""
    var = declared(name)
    v = _environ(environ).get(name)
    if v not in (None, ""):
        return v
    return var.default if default is _MISSING else default


def setting_float(name: str, default=_MISSING, environ=None) -> float | None:
    v = setting(name, default, environ)
    return None if v in (None, "") else float(v)


def setting_int(name: str, default=_MISSING, environ=None) -> int | None:
    v = setting(name, default, environ)
    return None if v in (None, "") else int(v)


def pairs(text: str | None) -> dict:
    """"A=x,B=y" -> {"A": "x", "B": "y"} (SEAT_HOSTS, RO_SIDES, RO_SEAT_CODES)."""
    return dict(x.split("=", 1) for x in (text or "").split(",") if "=" in x)


def process_environ(environ=None) -> dict:
    """A copy of this process's whole environment, for a child process the platform starts with it (core/launch.py:
    a seat's metering proxy gets its own credentials from it). Never read for an option."""
    return dict(_environ(environ))


def scrub(names=HIDDEN_ENV) -> None:
    """Drop names from this process's environment before any child starts (the practice service and the sandbox: a
    hidden seed or its salt never reaches a practice world)."""
    for k in names:
        os.environ.pop(k, None)


def process_default(name: str, value: str) -> None:
    """Set a declared process knob if unset (OMP_NUM_THREADS = 1 in a practice world's process)."""
    declared(name)
    os.environ.setdefault(name, value)


def _launch(name, n):
    """(name, n) of a program started by `game program` (core/client.py program_start), else None."""
    try:
        return (str(name)[:40], int(n)) if name and n else None
    except ValueError:
        return None


def seat_settings(environ=None) -> dict:
    """The seat's client settings (core/client.py, core/game.py): the service, the seat, the practice service, the
    harness's shell markers, the program directory, the session waits, a built-in player's seed, the rules file."""
    e = environ
    return {"sim_url": setting("SIM_URL", environ=e), "seat": setting("SEAT", environ=e),
            "practice_url": setting("PRACTICE_URL", environ=e),
            "agent_shells": tuple(x.strip() for x in (setting("RO_AGENT_SHELLS", environ=e) or "").split(",")
                                  if x.strip()),
            "program_dir": setting("RO_PROGRAM_DIR", environ=e),
            "program_launch": _launch(setting("RO_PROGRAM_NAME", environ=e), setting("RO_PROGRAM_LAUNCH", environ=e)),
            "session_wait_s": float(setting("RO_SESSION_WAIT_S", environ=e)),
            "session_connect_s": float(setting("RO_SESSION_CONNECT_S", environ=e)),
            "player_seed": int(setting("RO_PLAYER_SEED", environ=e)),
            "rules_file": setting("RO_RULES", environ=e)}


def seat_defaults() -> dict:
    """The declared defaults of the seat's settings (kind "seat"). tools/generate.py writes them into the seat's `game`
    command (core/game.py SEAT_ENV), which reads its settings with the same rule as seat_settings (a name's value, or
    its default when unset or empty) without importing this module: one `game` call is one short process (core
    0.5.3)."""
    return {n: v.default for n, v in ENV.items() if v.kind == "seat"}


# ------------------------------------------------------------------------------------------- the TaskSpec
@dataclass(frozen=True)
class TaskSpec:
    """A task's configuration as the core uses it. `options` has every key of OPTIONS; `timing` every key of
    TIMING_DEFAULTS; `overrides` = {"options.<key>" | "timing.<key>" | "match.<key>" | "team_channel": the value used}
    where the environment changed the file's value; `runtime` = deployment settings (act_rule, devgate); `data` = the
    file as read ({} without one); `path` = the file read (None without one).

    Core 0.4.0 (read from either schema): `match` = the match configuration's task part (sport, format, seats, sides,
    level, action_level, play, params, renderer; robots, platform from eo-taskspec/1 slots); `action` = D, L, K,
    batch, safe_action (only what the file declares: {} = the sport's own declarations); `review` = after, window_s,
    on_timeout, submitter, why_max_chars, plan_max_chars, windows_s (core 0.5.2: {unit end reason: seconds}, e.g.
    {"half_time": 600}; the other units take window_s) ({} = the defaults); `slots`, `sensors`, `termination`
    (None: not declared); `continuity` (fresh | persistent); `team_channel` (on | off)."""
    id: str | None
    sha256: str | None
    options: dict
    timing: dict
    overrides: dict
    runtime: dict = field(default_factory=dict)
    data: dict = field(default_factory=dict)
    path: str | None = None
    match: dict = field(default_factory=dict)
    action: dict = field(default_factory=dict)
    review: dict = field(default_factory=dict)
    slots: dict | None = None
    sensors: dict | None = None
    termination: dict | None = None
    continuity: str = "fresh"
    team_channel: str = "on"
    camera_latency_steps: int | None = None   # the declared camera latency (sensors; None: not declared)

    @property
    def protocol(self) -> str | None:
        """"realtime" / "turn" from the file's protocol id, None without a file."""
        p = str(self.data.get("protocol") or "")
        return "turn" if "turn" in p else "realtime" if p else None

    @property
    def action_layer(self) -> str | None:
        """skill | joint: the file's declaration (eo-taskspec/1), None without one."""
        return self.data.get("action_layer") or None

    @property
    def track(self) -> str | None:
        """athlete | engineer: the file's explicit declaration (eo-taskspec/1 requires it; load() refuses a file
        without it), never inferred from the action layers (fwspec_decisions_1020 #5: a single-layer sport's track is
        the task's to declare). None: no file, or a gen-1 file that does not state it."""
        return self.data.get("track") or None

    def layer_delay(self, default: int | None = None) -> int:
        """The action layer's planning budget L (eo-taskspec/1 action.layer_delay_steps); not declared: `default` (core
        0.4.1: the sport's declaration, sport.toml [timing] layer_delay_steps, core/spec.layer_delay), else UNDECIDED."""
        v = self.action.get("layer_delay_steps")
        if v is None:
            v = default
        return int(UNDECIDED["layer_delay_steps"] if v is None else v)

    def in_flight_per_robot(self, layer: int | None = None) -> int:
        """K (eo-taskspec/1 action.in_flight_per_robot); not declared: L + UNDECIDED in_flight_extra (= L + 1), with
        `layer` = the L in force (default: layer_delay()). Core 0.5.0: no reaction delay D in it."""
        v = self.action.get("in_flight_per_robot")
        if v is not None:
            return int(v)
        return (self.layer_delay() if layer is None else int(layer)) + int(UNDECIDED["in_flight_extra"])

    def safe_action(self) -> dict | None:
        """The task's safe action (eo-taskspec/1 action.safe_action), None: the sport's declaration."""
        return self.action.get("safe_action")

    def record(self) -> dict:
        """final.json `taskspec`: {"id", "sha256", "options", "overrides"} (+ variant_of / arm when present; schema
        when it is not ro-taskspec/1)."""
        out = {"id": self.id, "sha256": self.sha256, "options": dict(self.options), "overrides": dict(self.overrides)}
        for k in ("variant_of", "arm"):
            if self.data.get(k):
                out[k] = self.data[k]
        if self.data.get("schema") not in (None, SCHEMA):
            out["schema"] = self.data["schema"]
        return out

    def replace(self, options: dict | None = None, timing: dict | None = None, runtime: dict | None = None,
                **kw) -> "TaskSpec":
        """A copy with some options / timing / runtime values replaced, for an in-process service of the platform's
        own (a realtime practice world: no start barrier, reviews from any process; the practice check). Not an
        override: such a service never produces a result of the task."""
        return dataclasses.replace(self, options={**self.options, **(options or {})},
                                   timing={**self.timing, **(timing or {})},
                                   runtime={**self.runtime, **(runtime or {})}, **kw)


# ---------------------------------------------------------------------------------------------------- reading
_lock = threading.Lock()
_files: dict = {}                       # path -> (data, sha256) or None (no file)


def default_path(environ=None) -> Path:
    p = setting("RO_TASKSPEC", environ=environ)
    return Path(p) if p else ROOT.parent / "taskspec.json"


def reset():
    """Forget the parsed files (tests that write another taskspec.json)."""
    with _lock:
        _files.clear()


def _read(path: Path):
    key = str(path)
    with _lock:
        if key in _files:
            return _files[key]
    got = None
    if path.is_file():
        raw = path.read_bytes()
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError(f"{path}: a TaskSpec is a JSON object")
        if data.get("schema") not in SCHEMAS:
            raise ValueError(f"{path}: schema must be one of {SCHEMAS}, not {data.get('schema')!r}")
        got = (data, hashlib.sha256(raw).hexdigest())
    with _lock:
        _files[key] = got
    return got


def load(environ=None) -> TaskSpec:
    """The task's TaskSpec: taskspec.json (default_path), then the allowed environment overrides (each one that
    differs from the file is recorded). Raises ValueError on a value outside an option's choices (a broken task must
    not start)."""
    env = _environ(environ)
    path = default_path(env)
    got = _read(path)
    data, sha = got if got else ({}, None)
    have = got is not None
    file = read_eo(data) if data.get("schema") == SCHEMA_EO else read_ro(data)
    if data.get("track") is not None and data["track"] not in TRACKS:
        raise ValueError(f"{path}: track must be one of {TRACKS}, not {data['track']!r}")
    if data.get("schema") == SCHEMA_EO and not data.get("track"):
        raise ValueError(f"{path}: an eo-taskspec/1 file declares its track ({' | '.join(TRACKS)}); it is never "
                         "inferred")
    options = dict(DEFAULTS)
    if not have:                                     # no file: the behaviour before core 0.3.0 (module text)
        options["timing.t0"] = "service_start"
    for k, v in (file["options"] or {}).items():
        if k not in DEFAULTS:
            raise ValueError(f"unknown TaskSpec option {k!r}; the options are {list(OPTIONS)}")
        options[k] = check_option(k, v)
    timing = dict(TIMING_DEFAULTS)
    for k, v in (file["timing"] or {}).items():
        if k in timing:
            timing[k] = _seconds(k, v)
    proto = "turn" if "turn" in str(data.get("protocol") or "") else "realtime"
    relevant = RELEVANT[proto]
    overrides: dict = {}

    def over(key, value, before):
        if have and value != before and key in relevant:
            overrides[key] = value

    for k, names in OPTION_ENV.items():
        raw = _first(env, names)
        if raw is None:
            continue
        v = _option_env(k, raw)
        over(f"options.{k}", v, options[k])
        options[k] = v
    for k, names in TIMING_ENV.items():
        if k == "match_s" and data.get("schema") == SCHEMA_EO:
            continue                                 # eo-taskspec/1: the cap is wall_cap_s (RO_WALL_CAP_S), from t0
        raw = _first(env, names)
        if raw is None:
            continue
        v = _seconds(k, raw)
        over(f"timing.{k}", v, timing[k])
        timing[k] = v
    match = dict(file["match"])
    for k, name in MATCH_ENV.items():
        raw = env.get(name)
        if raw in (None, ""):
            continue
        v = _match_env(k, raw)
        if k in file["match"] and not (k == "level" and file["match"][k] is None):
            over(f"match.{k}", v, file["match"][k])
        match[k] = v
    team = file["team_channel"]
    raw = env.get(TEAM_CHANNEL_ENV)
    if raw not in (None, ""):
        v = "off" if raw.strip().lower() == "off" else "on"
        over("team_channel", v, team)
        team = v
    cam = camera_latency(file["sensors"])
    raw = env.get(SENSOR_ENV["camera_latency_steps"])
    if raw not in (None, ""):
        try:
            v = int(raw)
        except ValueError:
            v = -1
        if v < 0:
            raise ValueError(f"{SENSOR_ENV['camera_latency_steps']} must be a whole number of steps >= 0, not {raw!r}")
        over("sensors.camera_latency_steps", v, cam)
        cam = v
    runtime = {k: env.get(name) or default for k, (name, default) in RUNTIME_ENV.items()}
    return TaskSpec(id=file["id"], sha256=sha, options=options, timing=timing, overrides=overrides,
                    runtime=runtime, data=data, path=str(path) if have else None, match=match,
                    action=file["action"], review=file["review"], slots=file["slots"], sensors=file["sensors"],
                    termination=file["termination"], continuity=file["continuity"], team_channel=team,
                    camera_latency_steps=cam)


def camera_latency(sensors: dict | None) -> int | None:
    """The cameras' declared delivery latency in control steps (eo-taskspec/1 sensors.cameras[].latency_steps: the
    largest; a frame taken at step c is delivered at c + latency_steps), None when no camera is declared."""
    cams = [c for c in (sensors or {}).get("cameras") or [] if isinstance(c, dict)]
    vals = [int(c["latency_steps"]) for c in cams if c.get("latency_steps") is not None]
    return max(vals) if vals else None


def read_ro(data: dict) -> dict:
    """An ro-taskspec/1 file (or none: {}) as load() reads it."""
    match = {}
    for k in ("sport", "format", "level"):
        if k in data:
            match[k] = data[k]
    if data.get("seats"):
        match["seats"] = tuple(data["seats"])
    if "sides" in data:
        match["sides"] = dict(data["sides"]) if data.get("sides") else None
    # the action level is not in a gen-1 file (RCB_ACTION_LEVEL gives it; its `track` is a separate declaration)
    return {"id": data.get("id"), "options": data.get("options") or {}, "timing": data.get("timing") or {},
            "match": match, "action": {}, "review": {}, "slots": None, "sensors": None, "termination": None,
            "continuity": "fresh", "team_channel": "on"}


def read_eo(data: dict) -> dict:
    """An eo-taskspec/1 file (fwspec/taskspec.schema.yaml) mapped onto the TaskSpec: the options and timing keys the
    core already reads, the match configuration from the slots, and the new groups as they are."""
    t = data.get("timing") or {}
    sb = t.get("start_barrier") or {}
    practice = data.get("practice") or {}
    rv = data.get("review") or {}
    act = data.get("action") or {}
    if "reaction_delay_steps" in act:
        raise ValueError("eo-taskspec/1 action.reaction_delay_steps was removed in core 0.5.0 (decided 10-28): an act "
                         "takes effect at e = r + L (r: the step at which the service admits it, L: "
                         "action.layer_delay_steps); regenerate the task (tools/generate.py)")
    options = {"timing.t0": "barrier", "timing.match_cap": "void",
               # the lead 10-21: the review from the agent itself (submitter agent, the default); a Task that
               # declares any_seat_process keeps that research variant
               "review.source": "seat" if rv.get("submitter") == "any_seat_process" else "shell"}
    if t.get("slowdown") is not None:
        options["timing.slowdown"] = t["slowdown"]
    for k in ("access", "package"):
        if practice.get(k) is not None:
            options[f"practice.{k}"] = practice[k]
    if act.get("limits") is not None:
        options["act.limits"] = act["limits"]
    if (data.get("deliverables") or {}).get("final_program") is not None:
        options["final_program"] = data["deliverables"]["final_program"]
    timing = {k: t.get(k) for k in ("prepare_s", "wall_cap_s", "clock_s", "grace_s") if t.get(k) is not None}
    if sb.get("lead_s") is not None:
        timing["barrier_lead_s"] = sb["lead_s"]
    if sb.get("t0_wait_s") is not None:
        timing["t0_wait_s"] = sb["t0_wait_s"]
    if rv.get("window_s") is not None:
        timing["review_s"] = rv["window_s"]
    slots = data.get("slots")
    match = slot_match(slots) if slots else {}
    params = dict((data.get("world") or {}).get("params") or {})
    if "sport" in data:
        match["sport"] = data["sport"]
    # the sport's own format name (world.params.format; `format` is only the preset single / duel / team / multi)
    if params.get("format") or data.get("format"):
        match["format"] = params.get("format") or data["format"]
    # action_layer (skill | joint) and track are the task's declarations (TaskSpec.track / .action_layer); the
    # sport's own layer of an unmigrated plugin (high | low) still comes from RCB_ACTION_LEVEL: a single-layer sport
    # may be an Athlete task on its one ("low") layer (fwspec_decisions_1020 #5)
    rest = {k: v for k, v in params.items() if k not in ("format", "levels")}
    if rest:                                         # the sport's parameters (format / levels are the Host's)
        match["params"] = rest
    if (data.get("sensors") or {}).get("renderer"):
        match["renderer"] = data["sensors"]["renderer"]
    # the channel matters only on a side of two or more seats: off when such a side has it switched off
    team = "off" if any(len(s.get("seats") or []) > 1 and s.get("team_channel") is False
                        for s in (slots or {}).get("sides") or []) else "on"
    review = {k: rv[k] for k in ("after", "window_s", "on_timeout", "early_resume", "submitter", "why_max_chars",
                                 "plan_max_chars", "diagnostics", "windows_s") if k in rv}
    for reason, v in (review.get("windows_s") or {}).items():     # core 0.5.2: a review window by unit end reason
        _seconds(f"review.windows_s.{reason}", v)
    action = {k: act[k] for k in ("layer_delay_steps", "in_flight_per_robot", "batch", "safe_action") if k in act}
    return {"id": data.get("task_key") or data.get("id"), "options": options, "timing": timing, "match": match,
            "action": action, "review": review, "slots": slots, "sensors": data.get("sensors"),
            "termination": data.get("termination"), "continuity": data.get("continuity") or "fresh",
            "team_channel": team}


def slot_match(slots: dict) -> dict:
    """The match configuration's structure from eo-taskspec/1 slots: the entrant seats in order, seat -> side (None
    when every seat is its own side, named alike), seat -> robots, side -> platform controller (with its robots), and
    the platform opponent's level (L<n> -> n) when there is exactly one."""
    seats, sides, robots, platform = [], {}, {}, {}
    for side in slots.get("sides") or []:
        if side.get("kind") == "platform":
            platform[side["id"]] = dict(side.get("controller") or {}, robots=list(side.get("robots") or []))
            continue
        for seat in side.get("seats") or []:
            seats.append(seat["id"])
            sides[seat["id"]] = side["id"]
            robots[seat["id"]] = tuple(seat.get("robots") or ())
    out = {"seats": tuple(seats), "sides": sides if any(k != v for k, v in sides.items()) else None,
           "robots": robots, "platform": platform}
    levels = [str(c.get("level") or "") for c in platform.values()]
    if len(levels) == 1 and levels[0][:1] == "L" and levels[0][1:].isdigit():
        out["level"] = int(levels[0][1:])
    return out


def check_option(key: str, value):
    """A TaskSpec option's value, checked (ValueError otherwise); legacy names read as the new ones."""
    value = LEGACY_VALUES.get((key, value), value) if isinstance(value, str) else value
    if key in CHOICES:
        if value not in CHOICES[key]:
            raise ValueError(f"TaskSpec option {key} must be one of {CHOICES[key]}, not {value!r}")
        return value
    if key == "timing.slowdown":
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"TaskSpec option timing.slowdown must be a positive number, not {value!r}")
        return float(value)
    if key == "act.limits":
        if value == "derived":
            return value
        if (isinstance(value, dict) and set(value) == set(REQUEST_LIMIT_KEYS)
                and all(isinstance(value[x], int) and not isinstance(value[x], bool) and value[x] > 0
                        for x in REQUEST_LIMIT_KEYS)):
            return {x: int(value[x]) for x in REQUEST_LIMIT_KEYS}
        raise ValueError('TaskSpec option act.limits must be "derived" or {"rate_per_s": N, "open_requests": N} '
                         f"(positive integers), not {value!r}")
    raise ValueError(f"unknown TaskSpec option {key!r}")


def _first(environ, names):
    for n in names:
        v = environ.get(n)
        if v not in (None, ""):
            return v
    return None


def _option_env(key, raw: str):
    if key == "review.source":                       # RO_READY_FROM_SHELL: 1 = shell, anything else = seat
        return "shell" if raw.strip() == "1" else "seat"
    if key == "timing.slowdown":
        return check_option(key, float(raw))
    if key == "act.limits":
        raw = raw.strip()
        return check_option(key, raw if raw == "derived" else json.loads(raw))
    return check_option(key, raw.strip())


def _match_env(key, raw: str):
    if key == "seats":
        return tuple(x for x in raw.split(",") if x)
    if key == "sides":
        return pairs(raw) or None
    if key == "level":
        return int(raw)
    if key == "params":
        v = json.loads(raw)
        if not isinstance(v, dict):
            raise ValueError("RO_PARAMS must be a JSON object")
        return v
    if key == "action_level":
        return LAYERS.get(raw.strip(), raw.strip())
    return raw


def _seconds(key, v):
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"TaskSpec timing {key} must be a number of seconds, not {v!r}") from None
    if not math.isfinite(x) or x < 0:
        raise ValueError(f"TaskSpec timing {key} must be a finite number >= 0, not {v!r}")
    return x


# ------------------------------------------------------------------------------------------- the Run's binding
def fixture(seats=(), environ=None) -> dict:
    """The Run's binding of this match (the Fixture, resolved by the Runner): {"seed", "first", "salt", "seed_index",
    "modes": {seat: model | oracle | builtin}, "players": {seat: its player configuration}, "codes": {seat: an
    opponent pseudonym}, "fixture_id", "run_id", "continuity", "draws"} (draws, core 0.5.2: True when the fixture
    allows a draw: RO_DRAWS, or the fixture file's `draws`). The codes come from the fixture file (RO_FIXTURE:
    eo-fixture/1 `codes`) or RO_SEAT_CODES; none: {}."""
    e = _environ(environ)
    seed = setting("RO_SEED", environ=e)
    idx = setting("RO_SEED_INDEX", environ=e) or ""
    every = setting("RCB_PLAYER_MODE", environ=e)
    out = {"seed": int(seed) if seed not in (None, "") else None, "first": setting("RO_FIRST", environ=e),
           "salt": setting("RO_SEED_SALT", environ=e) or "",
           "seed_index": int(idx) if idx.lstrip("-").isdigit() else None,
           "modes": {s: setting(f"PLAYER_MODE_{s}", every, environ=e) for s in seats},
           "players": {s: setting(f"RO_PLAYER_CONFIG_{s}", environ=e) or "" for s in seats},
           "codes": pairs(setting("RO_SEAT_CODES", environ=e)), "fixture_id": None,
           "run_id": setting("RO_RUN_ID", environ=e), "continuity": None,
           "draws": (setting("RO_DRAWS", environ=e) or "").strip().lower() in ("1", "true", "yes", "on")}
    cont = setting("RO_CONTINUITY", environ=e)     # the Runner passes its continuity as JSON (FWINT2 10-20)
    try:
        cdoc = json.loads(cont) if cont else None
    except ValueError:
        cdoc = None
    if isinstance(cdoc, dict) and cdoc.get("mode"):
        out["continuity"] = {"mode": cdoc["mode"],
                             "carry_in": {str(s): {**{k: c.get(k) for k in ("position", "of", "carried")},
                                                   **({"paths": c["paths"]} if c.get("paths") else {})}
                                          for s, c in (cdoc.get("seats") or {}).items() if isinstance(c, dict)}}
        if isinstance(cdoc.get("disk"), dict):      # core 0.4.3: the persistent disk's soft cap (decided 10-21)
            out["continuity"]["disk"] = {"cap_bytes": int(cdoc["disk"]["cap_bytes"]),
                                         "warn_at": float(cdoc["disk"].get("warn_at") or 0.8)}
    path = setting("RO_FIXTURE", environ=e)
    if path:
        doc = json.loads(Path(path).read_text())
        if not isinstance(doc, dict):
            raise ValueError(f"{path}: a fixture is a JSON object")
        out["fixture_id"] = doc.get("fixture_id")
        out["codes"] = {str(k): str(v) for k, v in (doc.get("codes") or {}).items()} or out["codes"]
        if doc.get("continuity"):
            prev = out["continuity"] or {}            # the Runner's RO_CONTINUITY (of, carried, paths, disk) is kept
            out["continuity"] = {"mode": doc["continuity"],
                                 "carry_in": {s: (c if isinstance(c, str) else
                                                  {**((prev.get("carry_in") or {}).get(s) or {}),
                                                   **{k: c.get(k) for k in ("line", "position", "snapshot")}})
                                              for s, c in (doc.get("carry_in") or {}).items()}}
            if prev.get("disk"):
                out["continuity"]["disk"] = prev["disk"]
        if out["first"] is None and doc.get("first"):
            out["first"] = doc["first"]
        if "draws" in doc:                            # core 0.5.2: the fixture file's own choice wins
            out["draws"] = bool(doc.get("draws"))
    return out


def match_config(ts: TaskSpec, fx: dict | None = None, protocol: str | None = None):
    """The MatchConfig of the match (core/sport.py): the task part from the TaskSpec (the file, then the allowed
    overrides: TaskSpec.match), the Run's binding from the fixture (seed, first). The slowdown is the TaskSpec's
    timing.slowdown, the one path (realtime only). `protocol`: the sport's (a turn sport's slowdown is None)."""
    from .sport import MatchConfig                   # (a seat's ro_taskspec never calls this)
    m, fx = ts.match, fx or {}
    proto = protocol or ts.protocol or "realtime"
    return MatchConfig(sport=str(m.get("sport") or ""), format=str(m.get("format") or "duel"),
                       seats=tuple(m.get("seats") or ("A", "B")),
                       seed=int(fx["seed"]) if fx.get("seed") is not None else 1, first=fx.get("first") or None,
                       slowdown=ts.options.get("timing.slowdown") if proto == "realtime" else None,
                       level=int(m["level"]) if m.get("level") not in (None, "") else None,
                       action_level=str(m.get("action_level") or "high"), play=str(m.get("play") or "program"),
                       params=dict(m.get("params") or {}), sides=dict(m["sides"]) if m.get("sides") else None,
                       renderer=m.get("renderer") or None,
                       # core 0.4.0 (eo-taskspec/1 slots): the robots of each seat, the platform sides, the track
                       robots={s: tuple(r) for s, r in m["robots"].items()} if any((m.get("robots") or {}).values())
                       else None,
                       platform=dict(m["platform"]) if m.get("platform") else None, track=ts.track)


REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")      # the act request id (core/acts.py), here for the tools


__all__ = ["TaskSpec", "UNDECIDED", "load", "reset", "check_option", "default_path", "DEFAULTS", "OPTIONS", "CHOICES",
           "TIMING_DEFAULTS", "LEGACY_ENV", "SCHEMA", "SCHEMAS", "ENV", "ENV_PATTERNS", "setting", "declared",
           "fixture", "match_config", "seat_settings", "process_environ", "scrub", "process_default", "pairs"]
