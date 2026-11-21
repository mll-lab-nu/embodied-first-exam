"""What both protocols share: the match, seats and sides, the episode, worker processes, observations (whitelist,
cameras through the task's renderer, the team channel), the end of a match (fresh-process replay and its comparison)
and final.json (common validity fields + the sport's own fields)."""
from __future__ import annotations

import base64
import dataclasses
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import VERSION

# Embodied First Exam (RO_VERDICT_REPLAY=0, the task's compose): the match is graded by its live record; finalize runs no
# fresh-process replay (the replay video is drawn after the verdict, as before).
LIVE_VERDICT = __import__("os").environ.get("RO_VERDICT_REPLAY") == "0"
from . import floatmode
from . import deploys as deploys_mod
from . import parity as parity_mod
from . import platform_seat as platform_seat_mod
from . import reviews as reviews_mod
from . import score as score_mod
from . import seeds as seeds_mod
from . import sources
from . import spec as spec_mod
from . import taskspec as taskspec_mod
from .channel import TeamChannel
from .diaglog import Acts, safe
from .episode import Episode, source_sha
from .observe import CameraWorker, camera_opts, camera_scene, filter_fields, players_scene, reply_job
from .outcome import decide
from .outcome import with_draws as outcome_with_draws
from .phases import FORFEIT_REASONS, TERMINATION, PhaseRules
from .sport import PluginFault, Refused, layer_for
from .seats import Seat, validity_fields
from .spectator import Broadcast
from .sport import MatchBase
from .workers import ProcessWorker

ROOT = Path(__file__).resolve().parent
FINAL_SCHEMA = "ro-final/1"              # core 0.3.0: final.json's schema id
# every seat's review counts in final.json `seats` (the lead 10-21; `review_counts` gives them per seat by name)
REVIEW_COUNTS = ("reviews_due", "reviews_written", "reviews_missing", "reviews_refused_program")
CAMERA_KIND = "camera"           # the core's own render worker: the sport's cameras drawn by the task's renderer
# final.json compatibility (the readers of Season 1: live_board, the site extractors, regrade_transient, broadcast):
# every sport field (Match.final_fields(), also kept under "sport_fields") is lifted to the top level unless a core
# field has that name, and "score" is the by-side score unless the sport sets its own. A migrating sport keeps its
# legacy field names in final_fields(); a reader that needs a sport field whose name a core field took (e.g. a
# legacy "scores" table) reads sport_fields first (live_board does).
COMPAT = "v0.1-toplevel-aliases"


def platform_category(controller: dict) -> str:
    """A platform opponent's category for the seats (instruction_design_1020.md §6): its kind and level only."""
    kind = {"scripted": "a scripted player built into the world", "policy": "a reinforcement-learned player built into "
            "the world", "reference": "a reference player built into the world"}.get(str(controller.get("kind")),
                                                                                    "a player built into the world")
    lvl = controller.get("level")
    return f"{kind} (level {lvl})" if lvl else kind


def own_hook(obj, name) -> bool:
    """Does the sport's Match override MatchBase's default of `name`?"""
    f = getattr(type(obj), name, None)
    return f is not None and f is not getattr(MatchBase, name, None)


def public_spec(sport, cfg, seat, m, layer, decl) -> dict:
    """The sport's part of /spec: the action layer's commands, the camera definitions with their intrinsics, the
    rule constants of sport.toml [spec] and the tiebreak text, plus anything Sport.spec() adds."""
    out = {}
    schema = layer.schema(m, seat) if hasattr(layer, "schema") else {}
    if schema:
        out["actions"] = schema
    cams = m.cameras(seat) if own_hook(m, "cameras") else []
    if cams:
        from renderers.base import CameraDef
        out["cameras"] = [dict(c, **CameraDef.from_dict(c).intrinsics()) for c in cams]
    out.update(decl.get("spec") or {})
    if (decl.get("tiebreaks") or {}).get("text"):
        out["tiebreaks"] = decl["tiebreaks"]["text"]
    f = getattr(sport, "spec", None)
    if f is not None:
        out.update(f(cfg, seat, m))
    return out



def size_text(n: int) -> str:
    """A byte count as the specs write sizes (20GiB, 512MiB, ...)."""
    for suf, mult in (("TiB", 1 << 40), ("GiB", 1 << 30), ("MiB", 1 << 20), ("KiB", 1 << 10)):
        if n >= mult and n % mult == 0:
            return f"{n // mult}{suf}"
    return f"{n}B"



LIST_SUMMARY_EVERY_S = 30.0      # a mid-match summary's percentiles are recomputed at most this often (its n is current)


def summarize_list(v: list) -> dict:
    """A mid-match final.json's stand-in for a per-request list of numbers (core: the reporter's cost): its length and
    p50 / p99 / max (the graded final.json writes the list itself)."""
    import numpy as np
    n = len(v)
    if not n:
        return {"n": 0, "summary": True}
    try:
        x = np.asarray(v, dtype=float)
    except (TypeError, ValueError):
        return {"n": n, "summary": True}
    return {"n": n, "p50": round(float(np.percentile(x, 50)), 4), "p99": round(float(np.percentile(x, 99)), 4),
            "max": round(float(x.max()), 4), "summary": True}

class Later:
    """A final.json value computed after the service's lock is released (Service.write_final; core 0.4.0): the
    function runs on copies taken under the lock (the reaction report over every command row, percentiles, the
    seats' samples)."""
    __slots__ = ("fn",)

    def __init__(self, fn):
        self.fn = fn

    def __call__(self):
        return self.fn()


class Raw(str):
    """A final.json value already serialized (JSON text) under the lock: a snapshot of state other threads change."""


def camera_latency(ts, decl) -> int | None:
    """The declared camera latency L in control steps (core 0.4.0): the TaskSpec's (eo-taskspec/1 sensors, or the
    RO_CAMERA_LATENCY_STEPS override), else sport.toml [observation] latency_steps, else None (not declared)."""
    lat = getattr(ts, "camera_latency_steps", None)
    if lat is None:
        lat = (decl.get("observation") or {}).get("latency_steps")
    return None if lat is None else int(lat)


CAMERA_MODELS = ("request", "stream")


def camera_model(ts, decl, environ=None) -> str:
    """core 0.5.4: the cameras' delivery model: "stream" (every control step drawn in the background, an observation
    returns the frame taken L steps before at once; core/stream.py) when the TaskSpec says sensors.delivery =
    every_step (a gen-1 task: sport.toml [observation] camera_model = "stream"), else "request" (an observation draws
    the world as it is and holds the image until its available step, core 0.4.0)."""
    sens = getattr(ts, "sensors", None) or {}
    d = sens.get("delivery") if isinstance(sens, dict) else None
    if d is not None:
        return "stream" if d == "every_step" else "request"
    m = (decl.get("observation") or {}).get("camera_model", "request")
    if m not in CAMERA_MODELS:
        raise ValueError(f"sport.toml [observation] camera_model must be one of {CAMERA_MODELS}, not {m!r}")
    return m


def camera_ids(ts) -> list:
    """The task's declared camera names in order (eo-taskspec/1 sensors.cameras), else [None]."""
    return [c.get("id") for c in ((getattr(ts, "sensors", None) or {}).get("cameras") or [])
            if isinstance(c, dict)] or [None]


def frame_stamps(cams, steps, L, late=False) -> list:
    """observation.frames (eo-seat/1 ObserveReply): each camera's frames at the view steps, row by row (camera after
    camera, oldest left: the tile index) when the task names its cameras, else one entry per view step without a
    camera name or tile; available_step = step + L (None: no declared latency); `late` marks the newest frame."""
    newest = max(steps) if steps else None
    return [{"source": "camera", "camera": cam, "step": int(c), "available_step": None if L is None else int(c) + L,
             "late": bool(late) and c == newest, **({"tile": i * len(steps) + j} if cam is not None else {})}
            for i, cam in enumerate(cams) for j, c in enumerate(steps)]

class Views:
    """The observation path of a seat (D1, pilot-1018): the sport's whitelisted observation (+ the team channel), the
    camera job and its drawing (the seat's render worker, the core's camera worker with the task's renderer and the
    players' scene, or the sport's own drawing) and the reply images. The match service (Service) and the practice
    service (core/practice.py) both run THIS code, so that what a seat sees in a practice world is what it sees in the
    match (the same keys, the same cameras, the same renderer, images of the same size). Needs self.sport, plugin,
    cfg, m, decl, allowed, errors, finalized; init_views() sets the rest."""

    def init_views(self, seats, lazy_render=False):
        """The observation state and the seats' worker processes (render / plan / camera, one per kind and seat).
        lazy_render (the practice service): a seat's render worker starts with its first drawing, not here."""
        self.lazy = {}                           # (kind, seat) -> worker kind, started on first use
        ts = getattr(self, "ts", None)           # the task's team channel switch (an allowed override, core/taskspec.py)
        self.channel = TeamChannel(self.cfg, self.decl.get("team_channel"),
                                   switched_off=None if ts is None else ts.team_channel == "off")
        self.columns = int((self.decl.get("observation") or {}).get("columns", 2))
        self.workers = {}
        self.cameras = own_hook(self.m, "cameras") and not own_hook(self.m, "camera_job")
        self.renderer_name = self.cfg.renderer
        self.camera = None                       # in-process CameraWorker (turn protocol, or no render worker)
        self.render_lock = threading.Lock()      # in-process drawing: one at a time (it runs off the world lock)
        self.replies = own_hook(self.m, "reply_views") and self.cameras      # reply images (core 0.2.8)
        for kind in getattr(self.sport, "workers", ()):
            for s in seats:
                k = CAMERA_KIND if (kind == "render" and self.cameras) else kind
                if lazy_render and kind == "render":
                    self.lazy[kind, s] = k
                else:
                    self.workers[kind, s] = ProcessWorker(self.plugin, k, s, self.cfg.to_json())
        # core 0.5.6 (Chi 10-31): each seat's plan workers (RO_PLAN_WORKERS, sport.toml plan_workers; the first is
        # workers["plan", seat]), on the seat's own plan CPUs (core/workers.plan_cpus); a plan is a function of its job
        self.plan_pools = {}
        if "plan" in getattr(self.sport, "workers", ()) and getattr(getattr(self, "layer", None), "worker", True):
            from .workers import plan_workers
            extra = plan_workers() - 1
            for s in seats:
                if ("plan", s) in self.workers:
                    self.plan_pools[s] = [self.workers["plan", s]] + [
                        ProcessWorker(self.plugin, "plan", s, self.cfg.to_json()) for _ in range(extra)]
                    for i, w in enumerate(self.plan_pools[s][1:], 1):
                        self.workers["plan", f"{s}#{i}"] = w       # (closed with the others at the end)

    def plan_call(self, seat, job):
        """core 0.5.6: one plan in a free plan worker of `seat` (the first free one; all busy: the one asked least
        recently), off the lock; -> the layer's prepared result (its worker's time in worker_s)."""
        pool = self.plan_pools.get(seat) or [self.workers["plan", seat]]
        res = None
        for w in pool:
            try:
                res = w.call(job, wait=False)
                break
            except BlockingIOError:
                continue
        if res is None:
            rr = self.__dict__.setdefault("_plan_rr", {})
            i = rr.get(seat, 0) % len(pool)
            rr[seat] = i + 1
            res = pool[i].call(job, wait=True)
        if isinstance(res, dict):
            cpus = res.pop("cpus", None)
            if cpus is not None:
                self.__dict__.setdefault("plan_cpus_seen", {}).setdefault(seat, []).append(cpus)
        return res

    def camera_job(self, seat, query=None):
        """Under the lock: the job that draws `seat`'s images, and the metadata for the reply."""
        if not self.cameras:
            return self.m.camera_job(seat)
        cams = self.m.cameras(seat, query)
        if not cams:
            return None, {}
        return {"state": self.m.render_state(), "cams": cams, "columns": self.columns}, {}

    def draw(self, seat, job):
        """Off the lock: render a camera job, an observation or reply images (in the seat's render worker if the
        sport has one, where a second job of the seat queues; in-process jobs are drawn one at a time)."""
        if job is None or self.finalized:      # core 0.2.26: after finalization the render workers are closed
            return None
        if ("render", seat) in getattr(self, "lazy", {}):           # lazy_render: start it now
            with self.render_lock:
                k = self.lazy.pop(("render", seat), None)
                if k is not None:
                    self.workers["render", seat] = ProcessWorker(self.plugin, k, seat, self.cfg.to_json())
        if ("render", seat) in self.workers:
            try:
                return self.workers["render", seat].call(job, wait=True)
            except (BrokenPipeError, EOFError, ConnectionError, OSError):
                if self.finalized:                 # closed while this request ran: no images, never an error
                    return None
                raise
        with self.render_lock:
            if self.cameras:
                if self.camera is None:                 # core 0.5.4: the camera-only simplification as well
                    self.camera = CameraWorker(camera_scene(players_scene(self.sport, self.plugin, self.cfg),
                                                            self.plugin, self.decl),
                                               self.renderer_name, opts=camera_opts(self.decl))
                t = time.monotonic()
                out = self.camera.draw_job(job)
                out["worker_s"] = time.monotonic() - t
                return out
            return self.sport.worker_call(None, "render", job)

    def reply_job(self, seat, cmd, info):
        """With the lock held, right after Match.apply(seat, cmd) returned `info`: the job that draws the images of
        the action's result for its reply (Match.reply_views, core 0.2.8), or None."""
        if not self.replies:
            return None
        return reply_job(self.m, self.m.reply_views(seat, cmd, info), self.columns)

    def render_reply(self, seat, job) -> dict:
        """Off the lock: draw a reply job -> the reply's `observation` (image_png_b64 + tiles, as /observe; the key
        _png_bytes is for the caller's log and is removed by it)."""
        out = self.draw(seat, job) or {}
        obs = {"of": "the result of this action", "render_wall_s": round(out.get("worker_s", 0.0), 3)}
        if out.get("png"):
            obs["image_png_b64"] = base64.b64encode(out["png"]).decode()
        for k in ("tiles", "note"):
            if out.get(k):
                obs[k] = out[k]
        obs["_png_bytes"] = len(out.get("png") or b"")
        return obs

    def observation(self, seat, query=None, since=None) -> dict:
        """With the lock held: the sport's whitelisted observation (+ the team channel: the teammates' messages after
        the client's read mark `since`, else the recent ones, and the side's newest seq; reading never consumes)."""
        obs, bad = filter_fields(self.m.observe(seat, query), self.allowed)
        if bad:
            self.errors.append({"where": "observation", "error": f"fields outside the whitelist: {bad}"})
        if self.channel.enabled:
            obs["team_messages"], obs["team_seq"] = self.channel.messages(seat, self.m.k, self.m.dt or 1.0, since)
            self.delivered(seat, obs["team_messages"])
        return obs

    def delivered(self, seat, rows):
        """With the lock held: the teammates' messages `seat` gets for the first time (the match logs them)."""


class Service(Views, PhaseRules):
    protocol = ""

    def __init__(self, sport, plugin: str, cfg, data: Path, clock_s: float | None = None, ts=None, fixture=None,
                 environ=None):
        """`ts`: the task's TaskSpec (core/taskspec.py; default: taskspec.load()); `fixture`: the Run's binding
        (taskspec.fixture: seed salt and index, player modes, codes; default: read for these seats); `environ`: the
        environment the deployment settings are read from (default: the process's; an in-process service of the
        platform's own, e.g. a realtime practice world, gives its own)."""
        self.sport, self.plugin, self.cfg, self.data = sport, plugin, cfg, Path(data)
        self.data.mkdir(parents=True, exist_ok=True)
        self.environ = environ
        if ts is not None:
            self.ts = ts
        if getattr(self, "ts", None) is None:    # the task's options (core/taskspec.py, core 0.3.0): read once
            self.ts = taskspec_mod.load(environ)
        self.fx = fixture if fixture is not None else taskspec_mod.fixture(cfg.seats, environ)
        salt = self.fx.get("salt") or ""                     # a hidden official seed (core/seeds.py, core 0.2.14)
        self.hidden = ({"seed": int(cfg.seed), "salt": salt,
                        "commitment": seeds_mod.commitment(sport.name, cfg.seed, salt)} if salt else None)
        if self.hidden:                          # core 0.4.4: the world plays the keyed world seed (seeds.world_seed)
            self.hidden["world"] = seeds_mod.world_seed(sport.name, cfg.seed, salt)
            self.cfg = cfg = dataclasses.replace(cfg, seed=self.hidden["world"])
        self.decl = spec_mod.load(plugin)
        self.allowed = spec_mod.whitelist(self.decl)
        # core 0.4.7 (core/parity.py): the seat's timing, which a platform side plays under, in the match config
        # (so the episode header carries it and a replay builds the same platform side)
        self.cfg = cfg = parity_mod.with_timing(cfg, self.decl, self.ts, self.protocol or "realtime")
        # core 0.5.2: a fixture that allows a draw (a round-robin fixture) gives the world the sport's draw point
        self.cfg = cfg = outcome_with_draws(cfg, self.decl, bool(self.fx.get("draws")) or bool(cfg.draws))
        # core 0.5.6 (core/platform_seat.py): a platform side that plays as a player seat (sport.toml [platform_seat])
        self.cfg = cfg = platform_seat_mod.config(cfg, self.decl, self.ts, environ)
        self.m = sport.build(cfg)
        self.layer = sport.action_layer(layer_for(cfg.action_level))      # skill / joint read as high / low
        self.seats = {s: Seat(s, self.data, clock_s, cfg.side_of(s), mode=self.fx["modes"].get(s),
                              act_rule=self.ts.runtime.get("act_rule")) for s in cfg.seats}
        self.cond = threading.Condition(threading.RLock())
        self.t0 = time.monotonic()
        self.phase, self.reason, self.forfeiting = "prepare", None, None
        self.match_t0 = None                     # D2: monotonic time of the match start (the first run / begin)
        self.retired: list[str] = []
        self.errors, self.reviews, self.replay = [], [], {}
        self.finalizing = self.finalized = False
        self.final_seq = self.final_written = 0  # write_final: the newest snapshot wins (core 0.4.0)
        self.grading = False                     # finalize: the graded final.json is being written
        self.final_write_lock = threading.Lock()
        self.source_sha = source_sha(ROOT, *sport.source_dirs, *self.extra_source_dirs())
        self.versions = {"protocol": self.protocol_id, "core": VERSION, "sport": sport.revision,
                         "players": {s: self.fx["players"].get(s, "") for s in cfg.seats}}
        self.ep = Episode(self.data / "episode.jsonl", background=True)   # the world thread never waits for the disk
        self.diag = safe(self.ep.write)          # diagnostic rows (core/diaglog.py, core 0.2.25): never replayed
        self.acts = Acts(cfg.seats)
        self.deploys = deploys_mod.Deploys()     # D3: the deployment record (final.json `deploys`; record only)
        self.gate_path = self.ts.runtime.get("devgate") or None     # the development-world gate (Service.devgate)
        self.ep.write("header", cfg=self.cfg_json(), sport=sport.name, revision=sport.revision, protocol=self.protocol,
                      source_sha=self.source_sha, versions=self.versions, numeric=floatmode.current(),
                      player_modes={s: st.mode for s, st in self.seats.items()},
                      **({"seed_hidden": {"commitment": self.hidden["commitment"], "world": seeds_mod.WORLD}}
                         if self.hidden else {}),
                      taskspec={"id": self.ts.id, "sha256": self.ts.sha256}, **self.header_extra())
        self.init_phases()                       # core 0.3.0: the start barrier t0, seat states (core/phases.py)
        self.init_views(cfg.seats)
        # the review rules (the lead 10-21, core/reviews.py): the unit the messages name, every seat's counts
        self.review_unit = reviews_mod.unit_noun(self.decl, self.protocol)
        for st in self.seats.values():
            for k in REVIEW_COUNTS:
                st.stats.setdefault(k, 0)
        self.video_info: dict = {}
        self.bc = Broadcast(sport, cfg, self.m, self.decl, environ=environ, slowdown=cfg.slowdown)   # spectators
        self.bc.clean = self.public

    def cfg_json(self) -> dict:
        """The match configuration as the records show it: a hidden seed is written as -1 (core/seeds.py)."""
        d = self.cfg.to_json()
        if self.hidden:
            d["seed"] = seeds_mod.HIDDEN
        return d

    def public(self, obj):
        """What leaves the sim service (replies, final.json, the broadcast log): without a hidden seed or its salt
        (core/seeds.py scrub; core 0.2.14). Unchanged otherwise."""
        if not self.hidden:
            return obj
        return seeds_mod.scrub(obj, self.hidden["seed"], self.hidden["salt"], self.hidden["world"])

    def extra_source_dirs(self):
        """The renderer code is part of the match only when it draws the players' images."""
        return []

    # ------------------------------------------------------------------ helpers
    def reply_images(self, seat, job) -> dict:
        """Off the lock: draw a reply job -> the reply's `observation` (image_png_b64 + tiles, as /observe), logged."""
        obs = self.render_reply(seat, job)
        png_bytes = obs.pop("_png_bytes", 0)
        with self.cond:                          # information only (not replayed): what the seat was shown
            st = self.seats[seat]
            st.count("reply_images")
            st.sample("reply_render_s", obs["render_wall_s"])
            self.ep.write("reply_images", seat=seat, k=self.m.k, tiles=len(obs.get("tiles") or []),
                          png_bytes=png_bytes, render_wall_s=obs["render_wall_s"])
        return obs

    def delivered(self, seat, rows):
        """With the lock held: log the teammates' messages `seat` gets for the first time (team_delivered)."""
        for d in self.channel.deliver(seat, rows, self.m.k):
            self.diag("team_delivered", **d)

    def team_since(self, body):
        """The client's team-channel read mark in a request body (`team_since`), None when absent (400 if invalid)."""
        return self.channel.since_arg((body or {}).get("team_since"))

    def team(self, seat, body):
        """POST /<seat>/team {"since": n}: the teammates' messages after seq n (read-only; never consumes)."""
        with self.cond:
            code, out = self.channel.page(seat, self.m.k, (body or {}).get("since"))
            if code == 200:
                self.delivered(seat, out["messages"])
            return code, out

    def say(self, seat, body):
        with self.cond:
            if self.phase == "over":
                return 409, {"error": "the match is over"}
            code, out = self.channel.say(seat, body.get("text"), self.m.k, self.m.dt or 1.0)
            if code == 200:
                self.ep.write("team", seat=seat, k=self.m.k, seq=out["sent"]["seq"], text=body.get("text"))
            return code, out

    def refused_invalid(self, seat, exc):
        """With the lock held: a malformed action (core.sport.parse_action) -- the player's own error, counted and
        logged (not replayed), never a technical failure."""
        st = self.seats[seat]
        st.count("refused_invalid")
        if "refused" in st.stats:
            st.count("refused")
        self.ep.write("refused_invalid", seat=seat, k=self.m.k, error=str(exc)[:200], cause=exc.cause or None)

    def query_guard(self, seat, query, fn):
        """With the lock held: run fn (it reads the sport's observation / cameras with the player's query). With a
        query, any exception is the player's error (Refused, HTTP 400; the sport refuses what it cannot read);
        without one it is a technical failure as before."""
        if query is None:
            return fn()
        try:
            return fn()
        except Refused:
            raise
        except Exception as exc:  # noqa: BLE001
            err = Refused("invalid observation query (see /spec)")
            err.cause = f"{type(exc).__name__}: {str(exc)[:200]}"
            self.ep.write("refused_query", seat=seat, k=self.m.k, cause=err.cause)
            raise err from exc

    def failure(self, where, exc):
        """A request's technical failure: an error of the trial (not valid) and the end of the match. After the match
        is finalized (core 0.2.26) the trial is decided: a late request's failure is only logged, never an error (a
        player that observes after the end once voided a finished, replayed match)."""
        if self.finalized:
            print(f"after finalization, {where}: {type(exc).__name__}: {str(exc)[:200]}", file=sys.stderr, flush=True)
            return
        with self.cond:
            self.errors.append({"where": where, "error": str(exc)[:300]})
            self.ep.write("error", where=where, error=str(exc)[:300])
            self.end("technical_error")

    def forfeit(self, seat, why):
        """With the lock held: a core decision, logged for the replay (and recorded in the world if it wants)."""
        self.forfeiting = seat
        self.ep.write("forfeit", k=self.m.k, seat=seat, why=why)
        self.m.forfeit(seat, why)

    def active_sides(self):
        return [s for s in self.cfg.side_list() if s not in self.retired]

    def lose(self, seat, why) -> bool:
        """With the lock held: `seat`'s side leaves (resigned, no_show, the clock, a rule): the one exit rule
        (core/phases.py exit_side, core 0.4.0): the match ends if fewer than two sides remain in play, else the side
        retires and the others go on (True)."""
        return self.exit_side(seat, why)

    # ------------------------------------------------------------------ core 0.4.0: resign, the platform's stop
    def resign(self, seat, body=None):
        """POST /<seat>/resign {"confirm": true, "reason"?}: the seat's side leaves the match (eo-seat/1 9.7; any
        seat of a side resigns for it: taskspec.UNDECIDED resign). Two sides: the side loses and the match ends;
        more: the side retires (its robots perform the safe exit action) and the others go on."""
        body = body or {}
        if body.get("confirm") is not True:
            return 400, {"error": "resign needs {\"confirm\": true} (your side leaves the match: with two sides it "
                                  "loses)", "code": "bad_request"}
        reason = body.get("reason")
        if reason is not None and (not isinstance(reason, str) or len(reason) > 500):
            return 400, {"error": "reason must be a string of at most 500 characters", "code": "bad_request"}
        from . import taskspec as ts_mod
        with self.cond:
            early = self.before_t0(seat)
            if early:
                return early[0], {**early[1], "code": "before_t0"}
            if self.phase == "over":
                return 409, {"error": "the match is over", "code": "match_over"}
            st = self.seats[seat]
            side = self.cfg.side_of(seat)
            if st.retired or side in self.retired:
                return 409, {"error": "your side has already left the match", "code": "side_retired"}
            ident = deploys_mod.current()
            self.diag("resign", seat=seat, side=side, k=self.m.k, reason=reason, source=sources.tag(ident),
                      proc=(ident or {}).get("proc"))
            st.resigned = True
            if ts_mod.UNDECIDED["resign"] == "all_seats" and not all(
                    getattr(self.seats[x], "resigned", False) for x in self.cfg.seats_of(side)):
                return 200, {"accepted": "resign", "side": side, "effect": "pending",
                             "waiting_for": [x for x in self.cfg.seats_of(side)
                                             if not getattr(self.seats[x], "resigned", False)]}
            goes_on = self.exit_side(seat, "resigned")
            self.cond.notify_all()
            return 200, {"accepted": "resign", "side": side, "effect": "side_retires" if goes_on else "side_loses",
                         "now": self.resign_now(seat)}

    def resign_now(self, seat):
        """The `now` of a resign reply (the protocol's state)."""
        return self.state(seat)

    def abort(self, reason: str = "aborted", where: str | None = None):
        """The platform ends the match (SIGUSR2: a tool's stop, the Runner's integrity limit): a platform fault, void
        (reason aborted), never settled by the score."""
        with self.cond:
            if self.phase == "over":
                return
            self.fault("platform", str(reason or "aborted")[:64], where=where or "platform")
            self.end("aborted")

    # ------------------------------------------------------------------ D3: the deployment record
    def deploy_client(self, seat, k):
        """With the lock held: an act of `seat` arrived at step k from the program the request headers name
        (core/deploys.py; None headers: unidentified). Its version's row (a diagnostic `deploy` row when new)."""
        before = len(self.deploys.rows)
        row = self.deploys.client(seat, deploys_mod.current(), k)
        for r in self.deploys.rows[before:]:
            self.diag("deploy", **r)
        return row

    def end(self, reason, forfeiting=None):
        with self.cond:
            if self.finalizing:
                return
            if forfeiting is not None:
                self.forfeit(forfeiting, reason)
            self.on_end()
            self.phase, self.reason, self.finalizing = "over", reason, True
            self.ended_at = time.monotonic()         # core 0.4.9: the post-match window counts from here
            self.ep.write("end", k=self.m.k, reason=reason)
            self.settle_seats(reason, forfeiting)    # core 0.3.0: every seat's final status
            self.devgate("over")
            self.bc.frame(force=True)
            self.bc.event("end", reason=reason)
            self.cond.notify_all()
        threading.Thread(target=self.finalize, daemon=True).start()

    def on_end(self):
        pass

    def post_match_view(self) -> dict | None:
        """core 0.4.9 (decided 10-24): after the final whistle, the TaskSpec's post-match request (option
        final_program = post_match, its text and bounds in deliverables.post_match, written by the framework's
        instruction templates), in every reply that carries the seat's state; `left_s`: the window that is left. The
        result is already decided: nothing the seat does now changes it (affects_result false). None during the match,
        with another option, or when the TaskSpec gives no text. A harness adapter that re-wakes an exited session
        takes this as its full-time wake point: `text` is the whole prompt, `left_s` bounds the wake's wall time."""
        if self.phase != "over" or self.ts.options.get("final_program") != "post_match":
            return None
        pm = (self.ts.data.get("deliverables") or {}).get("post_match")
        if not isinstance(pm, dict) or not str(pm.get("text") or "").strip():
            return None
        window = float(pm.get("window_s") or 0.0)
        ended = getattr(self, "ended_at", None)
        left = max(0.0, window - (time.monotonic() - ended)) if ended is not None else window
        out = {"text": str(pm["text"]), "file": pm.get("file"), "window_s": window, "left_s": round(left),
               "affects_result": False}
        if pm.get("token_budget") is not None:
            out["token_budget"] = pm["token_budget"]
        return out

    def setting(self, name):
        """A deployment setting of this service (core/taskspec.py ENV)."""
        return taskspec_mod.setting(name, environ=self.environ)

    def finalize(self):
        try:
            if not self.ep.flush(timeout=float(self.setting("RO_REPLAY_TIMEOUT_S"))):   # every row in the file first
                raise RuntimeError("the episode writer did not flush in time")
            if LIVE_VERDICT:                     # Embodied First Exam: graded by the live match, no grading replay
                self.replay = {}
            else:
                subprocess.run([sys.executable, "-m", "core.episode", self.plugin, str(self.data)], check=True,
                               timeout=float(self.setting("RO_REPLAY_TIMEOUT_S")), cwd=ROOT.parent,
                               stdout=subprocess.DEVNULL)
                self.replay = json.loads((self.data / "replay_check.json").read_text())
        except Exception as exc:  # noqa: BLE001
            self.errors.append({"where": "replay", "error": str(exc)[:300]})
        with self.cond:                          # core 0.4.0: `finalized` once the graded final.json is written
            self.grading = True
            self.write_final()
            self.finalized = True
            self.cond.notify_all()
        ps = getattr(self, "pseats", None)
        if ps is not None:                       # core 0.5.6: the platform seats' programs
            ps.close()
        for w in self.workers.values():
            busy = w.lock.acquire(timeout=60)    # a reply image may still be drawn after the last action
            w.close()
            if busy:
                w.lock.release()
        if self.setting("RCB_RENDER_VIDEO") == "1":      # after graded-ready: spectators only, never an error
            try:
                self.ep.flush(timeout=60)
                subprocess.run([sys.executable, "-m", "core.spectator", self.plugin, str(self.data)], check=True,
                               timeout=float(self.setting("RCB_VIDEO_TIMEOUT_S")), cwd=ROOT.parent,
                               stdout=subprocess.DEVNULL)
                self.video_info = json.loads((self.data / "video.json").read_text())
            except Exception as exc:  # noqa: BLE001
                self.video_info = {"video": False, "why": str(exc)[:200]}
            with self.cond:
                self.write_final()

    def outcome(self):
        return decide(self.m, self.forfeiting, self.reason, self.cfg.side_list(), self.cfg.side_of, self.retired,
                      draw_after=self.cfg.draws)

    def continuous(self) -> dict | None:
        """With the lock held: the continuous score of every side (sport.toml [score], core/score.py; core 0.2.14). A
        side that forfeited or retired gets the declared forfeit value. A sport error here is a technical failure.
        None before the match is over (final.json is also written at the start and while it runs)."""
        if self.phase != "over":
            return None
        gone = list(self.retired)
        if self.forfeiting is not None and self.reason in FORFEIT_REASONS:
            gone.append(self.cfg.side_of(self.forfeiting))
        try:
            return score_mod.compute(self.m, self.decl, self.cfg.side_list(), gone)
        except Exception as exc:  # noqa: BLE001
            if not any(e.get("where") == "continuous_score" for e in self.errors):
                self.errors.append({"where": "continuous_score", "error": str(exc)[:300]})
            return None

    def seed_proof(self) -> dict | None:
        """A hidden official seed's record (core/seeds.py; core 0.2.14): the commitment of the seed and the salt the
        runner handed over (RO_SEED, RO_SEED_SALT: sim service only), and the index the runner names (RO_SEED_INDEX,
        information only). Neither the seed nor the salt is written; the verifier finds the commitment in the
        registered cell of the match's format and level."""
        if not self.hidden:
            return None
        return {"commitment": self.hidden["commitment"], "index": self.fx.get("seed_index")}

    def write_final(self):
        """final.json. Core 0.4.0 (the world thread's cost): the record is taken under the lock from cheap copies;
        the heavy fields (Later: the reaction report, percentiles), the serialization and the file are done after
        the lock is released (when the caller does not hold it), and a snapshot older than the one already written
        is dropped, so writers in several threads (the realtime reporter, the finalizer) never go back in time."""
        with self.cond:
            final, seq = self.final_record()
        self.write_record(final, seq)

    def write_record(self, final: dict, seq: int):
        """final.json from a record taken under the lock (final_record): its Later values computed, serialized and
        written atomically, unless a newer record was written already."""
        parts = []
        for k, v in final.items():
            if isinstance(v, Later):
                v = v()
            parts.append(json.dumps(k) + ": " + (v if isinstance(v, Raw) else json.dumps(v, default=float)))
        text = "{" + ", ".join(parts) + "}"
        with self.final_write_lock:
            if seq <= self.final_written:
                return
            tmp = self.data / "final.json.tmp"
            tmp.write_text(text)
            tmp.replace(self.data / "final.json")
            self.final_written = seq

    def final_record(self):
        """With the lock held: (final.json's record, its sequence number); Later values are computed after."""
        out = self.outcome()
        sha, cmds = self.m.state_digest(), self.ep.commands_sha()
        r = self.replay
        replay_ok = bool(r and r.get("state_sha") == sha and r.get("scores") == self.m.scores()
                         and r.get("winner") == out.winner and r.get("commands_sha") == cmds
                         and r.get("source_sha") == self.source_sha and r.get("k") == self.m.k)
        if LIVE_VERDICT:                         # Embodied First Exam: the live record is the verdict (no replay term)
            replay_ok = True
        v = validity_fields(self.seats, self.need_meter)
        single = len(self.cfg.side_list()) == 1
        complete = self.reason == "match_over" or (self.reason in FORFEIT_REASONS and
                                                   (out.winner is not None or single))
        graded = self.finalized or self.grading     # the finalizer's write is the graded one (core 0.4.0)
        valid = bool(graded and complete and replay_ok and not self.errors
                     and not any(v["meter_error"].values()) and not any(v["proxy_error"].values()))
        cont = self.continuous()
        valid = valid and not self.errors and not self.no_session_seats()   # FWTEAM 10-20: no_session is void
        self.final_facts = {"valid": valid, "replay_ok": replay_ok, "meter_error": any(v["meter_error"].values()),
                            "proxy_error": any(v["proxy_error"].values())}
        sport = self.m.final_fields()
        # copies (the file is written after the lock is released). Mid-match (not graded; the realtime reporter's
        # rewrite every second) each per-request list (act_s, obs_age_s, ...) is written as its summary
        # (summarize_list): copying and serializing the whole lists every second grew with the match and held the GIL
        # off the world thread (an 11 v 11 match: 24 ms at 1.56 MB). The graded final.json keeps the full lists.
        now = time.monotonic()
        cache = self.__dict__.setdefault("list_summaries", {})

        def summary(s, k, v):                    # mid-match: recomputed at most every LIST_SUMMARY_EVERY_S
            c = cache.get((s, k))
            if c is None or now - c[0] >= LIST_SUMMARY_EVERY_S:
                c = cache[(s, k)] = (now, summarize_list(v))
            return dict(c[1], n=len(v))
        seats = {s: {k: ((list(v) if graded else summary(s, k, v)) if isinstance(v, list) else v)
                     for k, v in st.stats.items()} for s, st in self.seats.items()}
        for s, extra in (sport.pop("seats", None) or {}).items():
            seats.setdefault(s, {}).update(extra)
        final = {"schema": FINAL_SCHEMA, "sport": self.sport.name, "protocol": self.protocol,
                 "revision": self.sport.revision,
                 "versions": self.versions, "source_sha": self.source_sha, "cfg": self.cfg_json(),
                 "seed": self.cfg_json()["seed"], "first": self.cfg.first, "action_level": self.cfg.action_level,
                 "play": self.cfg.play, "format": self.cfg.format,
                 "sides": {s: self.cfg.side_of(s) for s in self.cfg.seats}, "phase": self.phase,
                 "reason": self.reason, "forfeiting": self.forfeiting, "retired": list(self.retired),
                 "scores": self.m.scores(), "match_winner": out.winner, "decided_by": out.decided_by,
                 "ranking": out.ranking, "solo": out.solo,
                 "winner": out.winner if valid else None, "state_sha": sha, "commands_sha": cmds,
                 "steps": self.m.k,
                 **({"session_end_decides": True} if __import__("os").environ.get("RO_COLLECT_ENDS_MATCH") == "1"
                    else {}),
                 **({"graded_by": "live", "replays": 0, "verdict_replay": False} if LIVE_VERDICT else
                    {"deterministic": replay_ok, "replay_scores": r.get("scores")}),
                 "finalized": graded, "graded_ready": graded, "valid_trial": valid,
                 "technical_failure": not valid, "errors": self.errors, "seats": seats,
                 "joined": {s: st.joined for s, st in self.seats.items()}, "reviews": self.reviews,
                 "renderer": self.renderer_used(), "team_messages": len(self.channel.log),
                 "video": bool(self.video_info.get("video")), "video_info": self.video_info, "elapsed_s": round(time.monotonic() - self.t0, 1), **v, **self.extra_final(),
                 "continuous": cont, "seed_proof": self.seed_proof(),
                 "deploys": self.deploys.final(), "control_sources": self.deploys.sources(),
                 **({"deploys_overflow": self.deploys.overflow} if self.deploys.overflow else {}),
                 # core 0.3.0 (fw-v1): the task's options, the start barrier, the derived limits, every seat's
                 # status, every side's result and the core's reading of a failure (core/phases.py)
                 "taskspec": self.ts.record(), "t0": self.t0_info(), "limits": getattr(self, "limits", None),
                 "seat_status": self.seat_status(), "side_outcome": self.side_outcome(valid),
                 "failure_hint": self.failure_hint(self.final_facts),
                 # core 0.4.0 (impl/core; the world report's words, fwspec world-report.schema.yaml): how the
                 # match ended, the Host's exits and faults, the harness exits (events only), the reviews due /
                 # missing (the Judge's diagnostics)
                 "termination": TERMINATION.get(self.reason) if self.phase == "over" else None,
                 "exits": list(self.exits), "faults": list(self.faults),
                 "harness_exits": {x: list(v) for x, v in self.harness_exits.items()},
                 "review_missing": list(self.review_missing),
                 # the lead 10-21: per seat, the reviews due, written (accepted), missing and refused (sent by a
                 # program), so that the public review rate can be computed
                 "review_counts": self.review_counts(),
                 # core 0.4.0 (eo-world/1 Result): every side's status, score, rank and metrics
                 "result": self.result_record(out, valid),
                 "sport_fields": sport}
        compat = {k: v for k, v in sport.items() if k not in final}     # see COMPAT below
        if "score" not in final and "score" not in compat:
            compat["score"] = final["scores"]
        final.update(compat)
        final["compat"] = {"schema": COMPAT, "lifted": sorted(compat)}
        if self.hidden:                      # the sport's fields (a sport may record its seed): scrubbed
            for k in {"sport_fields", "video_info", "errors", *compat}:
                if k in final:
                    final[k] = self.public(final[k])
        # core 0.4.0: a snapshot. The seats' copies are serialized (and scrubbed) after the lock is released; every
        # other value is serialized now (Raw), since other threads go on changing what it refers to
        own = final["seats"]
        final["seats"] = Later(lambda: self.public(own))
        for k, v in final.items():
            if not isinstance(v, Later):
                final[k] = Raw(json.dumps(v, default=float))
        self.final_seq += 1
        return final, self.final_seq

    def renderer_used(self):
        if not self.cameras:
            return "sport"                       # the sport draws its own images (a stage-0 wrapper)
        import renderers
        return self.renderer_name or renderers.DEFAULT

    def need_meter(self, seat) -> bool:
        return seat.mode == "model" and seat.joined

    def extra_final(self) -> dict:
        return {}

    def header_extra(self) -> dict:
        """Protocol-specific fields of the episode header (realtime: its timing, core 0.2.23)."""
        return {}

    def robots_of(self, seat) -> list:
        """The robots `seat` controls: the Task's slots (MatchConfig.robots), else the plugin's own entity names
        (Match.entities, the compatibility fallback), else none named (one robot)."""
        r = self.cfg.robots_of(seat)
        return list(r) if r else list(self.m.entities(seat) or ())

    def review_gate(self, seat, why, plan, where: dict):
        """With the lock held, for a review (realtime: ready in a review window; turn-based: ready after an action):
        None when it may be accepted, else (code, reply). The lead's decision 10-21 (rule 3, core/reviews.py): a
        model seat's review comes from the agent's own tool call (review.source shell; else 403, counted
        reviews_refused_program); a refused review is recorded (a ready_refused row, reason program; the Judge reads
        those rows) and may be sent again within the window. The text is not checked. Built-in players are never
        refused."""
        st = self.seats[seat]
        if getattr(st, "mode", "model") != "model":
            return None
        ident = deploys_mod.current()
        src = sources.tag(ident)
        texts = {"why": str(why)[:300], "plan": str(plan)[:300]}
        if not sources.review_allowed(self.ts.options["review.source"], st.mode, src):
            st.count("reviews_refused_program")
            st.count("refused_ready_program")                 # the name the Judge's refusal summary reads
            self.diag("ready_refused", seat=seat, reason="program", source=src,
                      proc=(ident or {}).get("proc"), **where, **texts)
            return 403, {"error": reviews_mod.program_message(self.review_unit), "code": "review_from_program"}
        return None

    def review_authorship(self) -> str:
        """/spec: who writes a review (the lead 10-21; the TaskSpec's review.source)."""
        if self.ts.options["review.source"] == "shell":
            return ("you write it yourself, with `game ready` from your own tool call: a review sent by one of your "
                    "programs is refused (403) and you may send it again yourself within the window; its text is "
                    "recorded")
        return "any process of your seat may send it (a research variant), its source and text are recorded"

    def review_counts(self) -> dict:
        """With the lock held: final.json `review_counts` per seat (the lead 10-21)."""
        out = {}
        for s, st in self.seats.items():
            g = st.stats.get
            out[s] = {"due": g("reviews_due", 0), "written": g("reviews_written", 0), "missing": g("reviews_missing", 0),
                      "refused_program": g("reviews_refused_program", 0), "mode": getattr(st, "mode", None)}
        return out

    def plugin_fault(self, seat, exc):
        """With the lock held (core 0.4.0, eo-world/1): the plugin failed on `seat`'s request (PluginFault): a fault of
        class plugin for the Judge (final.json `faults`), counted per seat; the act is not executed, the match goes
        on."""
        self.seats[seat].count("plugin_faults")
        self.fault("plugin", "plugin_exception", where=getattr(exc, "where", None) or "parse_action",
                   note=getattr(exc, "cause", "") or str(exc), seat=seat)

    def safe_action(self) -> dict | None:
        """/spec `safe_action`: the TaskSpec's (eo-taskspec/1 action.safe_action), else the sport's declaration
        (sport.toml [safe_action]), else None."""
        return self.ts.safe_action() or self.decl.get("safe_action") or None

    def exit_mode(self) -> str:
        """The safe state of the robots of a side that left a match that goes on (safe_action on_exit of the task's
        track; default hold)."""
        sa = self.safe_action() or {}
        own = sa.get(self.cfg.track or "") if isinstance(sa.get(self.cfg.track or ""), dict) else sa
        return str((own or {}).get("on_exit") or "hold")

    def failsafe(self, side):
        """With the lock held, once a side retired in a match that goes on: Match.failsafe for each of its seats (the
        safe exit command, applied and logged as a command row: the replay applies it at the same step)."""
        mode = self.exit_mode()
        for s in self.cfg.seats_of(side):
            cmd = self.m.failsafe(s, mode)
            if cmd:
                self.ep.write("cmd", k=self.m.k, seat=s, cmd=cmd)
                self.m.apply(s, cmd)
                self.diag("failsafe", seat=s, k=self.m.k, mode=mode)

    def result_record(self, out, valid: bool) -> dict:
        """final.json `result` (core 0.4.0, eo-world/1 Result): Match.result() (or the compatibility default from
        the older hooks) with the Host's decisions over it: the ranking of a decided match (core/outcome.py), and a
        side that resigned, did not show or retired is `retired`; a void match keeps the sides' play but no rank."""
        try:
            res = self.m.result()
        except Exception as exc:  # noqa: BLE001  (the record only; the Judge sees the fault, once)
            if not any(f.get("code") == "result_exception" for f in self.faults):
                self.fault("plugin", "result_exception", where="result", note=f"{type(exc).__name__}: {exc}")
            res = {"final": False, "decided_by": "", "sides": {}}
        res = dict(res or {})
        sides = {str(k): dict(v) for k, v in (res.get("sides") or {}).items()}
        for side in self.cfg.side_list():
            sides.setdefault(side, {"status": "playing", "score": None, "rank": None})
        over = self.phase == "over"
        if over and out.draw:                    # core 0.5.2: a draw ranks every side first
            for side in sides:
                sides[side]["rank"] = 1
        elif over and out.winner is not None and len(sides) == 2:     # two sides (a platform side too): the winner
            for side in sides:
                sides[side]["rank"] = 1 if side == out.winner else 2
        elif over and out.ranking:
            for i, side in enumerate(out.ranking):
                if side in sides:
                    sides[side]["rank"] = i + 1
        for side in self.retired:
            if side in sides:
                sides[side]["status"] = "retired"
        if over and self.forfeiting is not None and self.reason in ("resigned", "no_show", "clock"):
            side = self.cfg.side_of(self.forfeiting)
            if side in sides:
                sides[side]["status"] = "retired"
        if over:                                 # a side still in play: finished when the match was decided (by
            done = self.reason in ("match_over", "resigned", "no_show", "clock")     # the rules or an exit)
            for side, v in sides.items():
                if v.get("status") == "playing":
                    v["status"] = "finished" if done else "dnf"
        if not valid:
            for v in sides.values():
                v["rank"] = None
        res["sides"] = sides
        res["final"] = bool(over and self.reason == "match_over")
        res.setdefault("decided_by", out.decided_by or "")
        res.pop("detail", None)                      # = sport_fields (final_fields), already in final.json
        return res

    def parity_final(self) -> dict:
        """With the lock held (core 0.4.7, core/parity.py): every platform side's measured timing (the queue's for
        Match.platform_commands, the plugin's Match.platform_report for a side inside the world) against the seat's
        timing and the sport's [[asymmetry]] declarations: {side: {report..., differences, undeclared}}."""
        reports: dict = {}
        sched = getattr(self, "sched", None)
        for side, rep in (sched.parity_report() if sched is not None and hasattr(sched, "parity_report")
                          else {}).items():
            reports[side] = rep
        try:
            own = self.m.platform_report() if own_hook(self.m, "platform_report") else {}
        except Exception as exc:  # noqa: BLE001  (a report never breaks the match)
            own = {"_error": {"error": f"{type(exc).__name__}: {exc}"}}
        for side, rep in (own or {}).items():
            reports[str(side)] = rep if side not in reports else {**reports[side], "world": rep}
        if not reports:
            return {}
        timing = parity_mod.seat_timing(self.cfg, self.decl)
        dec = parity_mod.declared_for(self.decl, self.cfg.format, self.cfg.level,
                                      parity_mod.track_of(self.cfg, self.decl))
        out = {}
        for side, rep in reports.items():
            diffs = parity_mod.compare(rep, timing, dec)
            out[side] = {**rep, "differences": diffs, "undeclared": len(parity_mod.undeclared(diffs))}
        return out

    def slots_view(self, seat) -> dict:
        """/spec `slots` (eo-seat/1 9.8; core 0.4.0, IMPL-CORE item 7): your seat, side and robots; your teammates
        and the opposing sides by their pseudonyms only (the fixture's codes: RO_FIXTURE / RO_SEAT_CODES; empty when
        the Run gives none), never a model or harness name; a platform opponent by its category."""
        codes = self.fx.get("codes") or {}
        side = self.cfg.side_of(seat)
        out = {"you": {"seat": seat, "side": side, "robots": self.robots_of(seat)},
               "teammates": [{"seat": x, "code": codes.get(x, ""), "robots": self.robots_of(x)}
                             for x in self.cfg.seats_of(side) if x != seat],
               "opponents": []}
        for other in self.cfg.side_list():
            if other == side:
                continue
            seats = self.cfg.seats_of(other)
            out["opponents"].append({"side": other, "kind": "entrant",
                                     "seats": [{"seat": x, "code": codes.get(x, "")} for x in seats],
                                     "robots": [r for x in seats for r in self.robots_of(x)]})
        platform = getattr(self.cfg, "platform", None) or {}
        for pside, c in platform.items():
            out["opponents"].append({"side": pside, "kind": "platform", "category": platform_category(c),
                                     "robots": list(c.get("robots") or []), "parity": self.parity_text()})
        if not platform and len(self.cfg.side_list()) == 1 and self.m.tiebreaks():
            lvl = f" (level L{self.cfg.level})" if self.cfg.level is not None else ""
            out["opponents"].append({"side": "opponent", "kind": "platform",
                                     "category": f"a player built into the world{lvl}", "robots": [],
                                     "parity": self.parity_text()})
        return out

    def parity_text(self) -> dict:
        """/spec slots: a platform opponent's timing and information against yours (core 0.4.7, core/parity.py), with
        the sport's declared asymmetries of this level ([[asymmetry]])."""
        if not parity_mod.checked(self.decl):
            return {"rule": "not yet checked for this sport (the platform opponents' timing and information may "
                            "differ from yours)", "declared_asymmetries": "none"}
        timing = parity_mod.seat_timing(self.cfg, self.decl)
        lines = parity_mod.asymmetry_lines(self.decl, self.cfg.format, parity_mod.track_of(self.cfg, self.decl),
                                           self.cfg.level)
        return {"rule": parity_mod.rule_text(timing, getattr(self.m, "dt", None) or None),
                "declared_asymmetries": lines or "none"}

    def continuity_view(self, seat) -> dict:
        """/spec `continuity`: fresh, or persistent and this seat's place in its line (the fixture's carry_in), what is
        carried and the persistent disk's soft cap (disk_cap, warn_at; core 0.4.3, decided 10-21)."""
        c = self.fx.get("continuity") or {}
        out = {"mode": c.get("mode") or self.ts.continuity}
        ci = (c.get("carry_in") or {}).get(seat)
        if isinstance(ci, dict) and ci.get("position"):
            out["position"] = int(ci["position"])
            if ci.get("of"):                         # the line's planned length (the Runner's RO_CONTINUITY)
                out["of"] = int(ci["of"])
        if isinstance(ci, dict) and ci.get("carried"):
            out["carried"] = list(ci["carried"])
        disk = c.get("disk") if out["mode"] == "persistent" else None
        if disk:
            out["disk_cap"] = size_text(disk["cap_bytes"])
            out["warn_at"] = disk["warn_at"]
        return out

    def disk_view(self, seat) -> dict | None:
        """GET status `disk` of a persistent match (core 0.4.3, decided 10-21): the soft cap, the warning fraction and
        what the snapshot counts (the Entry's include / exclude / skip paths), from which `game status` in the seat
        computes the use (used_bytes, warn). None in a fresh match."""
        c = self.fx.get("continuity") or {}
        disk = c.get("disk")
        if c.get("mode") != "persistent" or not disk:
            return None
        ci = (c.get("carry_in") or {}).get(seat)
        paths = (ci or {}).get("paths") if isinstance(ci, dict) else None
        return {"cap_bytes": int(disk["cap_bytes"]), "warn_at": float(disk["warn_at"]),
                "counts": {k: list((paths or {}).get(k) or []) for k in ("include", "exclude", "skip")}}

    def result_rule(self) -> dict:
        """/spec `result` (core 0.5.2): whether this match may end in a draw (the fixture's choice, e.g. a round-robin
        fixture of a sport with a draw point) or is always decided by the sport's tiebreaks."""
        order = list((self.decl.get("tiebreaks") or {}).get("order") or [])
        if self.cfg.draws:
            used = order[:order.index(self.cfg.draws) + 1] if self.cfg.draws in order else [self.cfg.draws]
            return {"draws": True, "draw_after": self.cfg.draws, "tiebreaks": used,
                    "rule": f"this match may end in a draw: level after {self.cfg.draws} it is over (the later "
                            "tiebreaks are not played)"}
        return {"draws": False, "tiebreaks": order,
                "rule": "this match is always decided: a level match goes on through the tiebreaks in order"}

    def spec(self, seat, body=None):
        # core 0.4.0 (eo-seat/1 9.2): /spec names no player: `versions` without the seats' player configurations
        versions = {k: v for k, v in self.versions.items() if k != "players"}
        out = {"seat": seat, "side": self.cfg.side_of(seat), "protocol": self.protocol_id,
               "revision": self.sport.revision, "versions": versions, "action_level": self.cfg.action_level,
               "play": self.cfg.play, "format": self.cfg.format, **self.spec_core(),
               **public_spec(self.sport, self.cfg, seat, self.m, self.layer, self.decl)}
        out["slots"] = self.slots_view(seat)
        out["first"] = self.cfg.first
        out["track"] = self.ts.track
        out["continuity"] = self.continuity_view(seat)
        out["result"] = self.result_rule()
        sa = self.safe_action()
        if sa:                                   # core 0.4.0 (eo-seat/1 9.8): what the robots do when silent / exited
            out["safe_action"] = sa
        if getattr(self, "obs_latency", None) is not None:      # core 0.4.0: the cameras' delivery latency (realtime)
            out["sensors"] = {"camera_latency_steps": self.obs_latency,
                              "rule": "an observation's newest frame, taken at step c, is delivered at step c + "
                                      f"{self.obs_latency} (never earlier; observation.frames give each frame's step "
                                      "and available_step; `late` when the drawing missed it); its state (`now`) is the "
                                      "world's when delivered"}
        lim = (getattr(self, "limits", None) or {}).get(seat)
        if lim:                                  # core 0.3.0: this seat's HTTP limits (core/acts.derive_limits);
            # request_limits, not limits: several sports' /spec has its own `limits` (the robot's joint limits)
            k_cap = lim.get("in_flight_per_robot", lim.get("in_flight_per_entity", 1))
            out["request_limits"] = {"rate_per_s": lim["rate_per_s"], "open_requests": lim["open_requests"],
                             "in_flight_per_robot": k_cap, "in_flight_per_entity": k_cap, "robots": lim["robots"],
                             "rule": "per seat: at most rate_per_s requests per second (every endpoint) and "
                                     f"open_requests open requests; at most {k_cap} act(s) per robot received and "
                                     "not yet in effect (429 in_flight); a request over a limit gets a bare 429 "
                                     "(retry it: game and ro_client do)"}
        out["taskspec"] = {"id": self.ts.id, "options": dict(self.ts.options)}      # core 0.3.0
        out["session"] = self.session_rule()
        if self.channel.enabled:
            out["team_channel"] = {"say": "POST /<seat>/say {'text': ...}", "max_bytes": self.channel.max_bytes,
                                   "min_interval_s": self.channel.min_interval_s,
                                   "max_messages": self.channel.max_messages,
                                   "read": ("observe / status show `team_messages` (from, seq, k, text) and `team_seq` "
                                            "(the newest seq); reading never consumes: send team_since = the "
                                            "largest seq you have (observe / wait body, status ?team_since=N) to get "
                                            "only newer ones, else you get the recent ones (the last "
                                            f"{self.channel.recent_s:g} game seconds, at most "
                                            f"{self.channel.recent_max}); POST /<seat>/team {{'since': n}} pages "
                                            "through the log"),
                                   "teammates": [s for s in self.cfg.seats_of(self.cfg.side_of(seat)) if s != seat]}
        return 200, out
