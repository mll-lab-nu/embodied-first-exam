"""What both protocols share: the match, seats and sides, the episode, worker processes, observations (whitelist,
cameras through the task's renderer, the team channel), the end of a match (fresh-process replay and its comparison)
and final.json (common validity fields + the sport's own fields)."""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import VERSION
from . import score as score_mod
from . import seeds as seeds_mod
from . import spec as spec_mod
from .channel import TeamChannel
from .diaglog import Acts, safe
from .episode import Episode, source_sha
from .observe import CameraWorker, filter_fields, players_scene, reply_job
from .outcome import decide
from .sport import Refused
from .seats import Seat, validity_fields
from .spectator import Broadcast
from .sport import MatchBase
from .workers import ProcessWorker

ROOT = Path(__file__).resolve().parent


class _NoReplay(Exception):
    pass


def verdict_replay() -> bool:
    """robot_coding_bench (owner 2026-10-17, board 0151): standard and standard-realtime are graded by the sim
    sidecar's live record only. RO_VERDICT_REPLAY=0 (the task's compose file): no fresh-process grading replay; the
    verdict (valid_trial, winner) is the live match's; final.json says so (verdict_replay false, deterministic null).
    Unset or 1: RoboOlympics' own rule (the replay must agree)."""
    return os.environ.get("RO_VERDICT_REPLAY", "1") != "0"


FORFEIT_REASONS = ("ready_timeout", "clock", "abandoned", "no_show")
CAMERA_KIND = "camera"           # the core's own render worker: the sport's cameras drawn by the task's renderer
# final.json compatibility (the readers of Season 1: live_board, the site extractors, regrade_transient, broadcast):
# every sport field (Match.final_fields(), also kept under "sport_fields") is lifted to the top level unless a core
# field has that name, and "score" is the by-side score unless the sport sets its own. A migrating sport keeps its
# legacy field names in final_fields(); a reader that needs a sport field whose name a core field took (e.g. a
# legacy "scores" table) reads sport_fields first (live_board does).
COMPAT = "v0.1-toplevel-aliases"


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


class Service:
    protocol = ""

    def __init__(self, sport, plugin: str, cfg, data: Path, clock_s: float | None = None):
        self.sport, self.plugin, self.cfg, self.data = sport, plugin, cfg, Path(data)
        self.data.mkdir(parents=True, exist_ok=True)
        self.decl = spec_mod.load(plugin)
        self.allowed = spec_mod.whitelist(self.decl)
        self.m = sport.build(cfg)
        self.layer = sport.action_layer(cfg.action_level)
        self.seats = {s: Seat(s, self.data, clock_s, cfg.side_of(s)) for s in cfg.seats}
        self.cond = threading.Condition(threading.RLock())
        self.t0 = time.monotonic()
        self.phase, self.reason, self.forfeiting = "prepare", None, None
        self.retired: list[str] = []
        self.errors, self.reviews, self.replay = [], [], {}
        self.finalizing = self.finalized = False
        self.channel = TeamChannel(cfg, self.decl.get("team_channel"))
        self.columns = int((self.decl.get("observation") or {}).get("columns", 2))
        self.source_sha = source_sha(ROOT, *sport.source_dirs, *self.extra_source_dirs())
        self.versions = {"protocol": self.protocol_id, "core": VERSION, "sport": sport.revision,
                         "players": {s: os.environ.get(f"RO_PLAYER_CONFIG_{s}", "") for s in cfg.seats}}
        salt = os.environ.get("RO_SEED_SALT", "")            # a hidden official seed (core/seeds.py, core 0.2.14)
        self.hidden = ({"seed": int(cfg.seed), "salt": salt,
                        "commitment": seeds_mod.commitment(sport.name, cfg.seed, salt)} if salt else None)
        self.ep = Episode(self.data / "episode.jsonl")
        self.diag = safe(self.ep.write)          # diagnostic rows (core/diaglog.py, core 0.2.25): never replayed
        self.acts = Acts(cfg.seats)
        self.ep.write("header", cfg=self.cfg_json(), sport=sport.name, revision=sport.revision, protocol=self.protocol,
                      source_sha=self.source_sha, versions=self.versions,
                      player_modes={s: st.mode for s, st in self.seats.items()},
                      **({"seed_hidden": {"commitment": self.hidden["commitment"]}} if self.hidden else {}),
                      **self.header_extra())
        self.workers = {}
        self.cameras = own_hook(self.m, "cameras") and not own_hook(self.m, "camera_job")
        self.renderer_name = cfg.renderer
        self.camera = None                       # in-process CameraWorker (turn protocol, or no render worker)
        self.render_lock = threading.Lock()      # in-process drawing: one at a time (it runs off the world lock)
        self.replies = own_hook(self.m, "reply_views") and self.cameras      # reply images (core 0.2.8)
        for kind in getattr(sport, "workers", ()):
            for s in cfg.seats:
                k = CAMERA_KIND if (kind == "render" and self.cameras) else kind
                self.workers[kind, s] = ProcessWorker(plugin, k, s, cfg.to_json())
        self.video_info: dict = {}
        self.bc = Broadcast(sport, cfg, self.m, self.decl, slowdown=cfg.slowdown)   # spectators only
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
        return seeds_mod.scrub(obj, self.hidden["seed"], self.hidden["salt"])

    def extra_source_dirs(self):
        """The renderer code is part of the match only when it draws the players' images."""
        return []

    # ------------------------------------------------------------------ helpers
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
        if ("render", seat) in self.workers:
            try:
                return self.workers["render", seat].call(job, wait=True)
            except (BrokenPipeError, EOFError, ConnectionError, OSError):
                if self.finalized:                 # closed while this request ran: no images, never an error
                    return None
                raise
        with self.render_lock:
            if self.cameras:
                if self.camera is None:
                    self.camera = CameraWorker(players_scene(self.sport, self.plugin, self.cfg),
                                               self.renderer_name)
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

    def reply_images(self, seat, job) -> dict:
        """Off the lock: draw a reply job -> the reply's `observation` (image_png_b64 + tiles, as /observe)."""
        out = self.draw(seat, job) or {}
        obs = {"of": "the result of this action", "render_wall_s": round(out.get("worker_s", 0.0), 3)}
        if out.get("png"):
            obs["image_png_b64"] = base64.b64encode(out["png"]).decode()
        for k in ("tiles", "note"):
            if out.get(k):
                obs[k] = out[k]
        with self.cond:                          # information only (not replayed): what the seat was shown
            st = self.seats[seat]
            st.count("reply_images")
            st.sample("reply_render_s", obs["render_wall_s"])
            self.ep.write("reply_images", seat=seat, k=self.m.k, tiles=len(obs.get("tiles") or []),
                          png_bytes=len(out.get("png") or b""), render_wall_s=obs["render_wall_s"])
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
        """With the lock held: `seat` loses (review time, clock, abandonment). With more than two sides the sport may
        let the match go on without that side (Match.retire); then True, else the match ends."""
        side = self.cfg.side_of(seat)
        if len(self.active_sides()) > 2 and self.m.retire(side, why):
            self.retired.append(side)
            for s in self.cfg.seats_of(side):
                self.seats[s].retired = True
            self.ep.write("retire", k=self.m.k, seat=seat, side=side, why=why)
            self.cond.notify_all()
            return True
        self.end(why, seat)
        return False

    def start_window(self) -> float:
        return float(os.environ.get("START_TIMEOUT_S", "1800"))

    def start_rule(self) -> dict:
        """The start window as /spec states it (both protocols)."""
        if len(self.cfg.side_list()) == 1:
            return {"window_s": self.start_window(),
                    "rule": "the window opens when the match service starts; if you have not started when it closes, "
                            "or your session ends before you start, you lose the match (no_show)"}
        return {"window_s": self.start_window(),
                "rule": "the match begins when every seat has started; the window opens with the first start; a side "
                        "that has not started when it closes, or when every player session has ended, loses the match "
                        "(no_show); if no side starts, the match does not count"}

    def absent_sides(self) -> list:
        """With the lock held: the sides (not retired) of which some seat has not started, in seat order."""
        absent = []
        for s in self.cfg.seats:
            side = self.cfg.side_of(s)
            if not self.seats[s].joined and side not in self.retired and side not in absent:
                absent.append(side)
        return absent

    def close_start_window(self, at="start_timeout") -> bool:
        """With the lock held, when the start window ran out in prepare (core rule 5, docs/framework_zh.md §9; core
        0.2.2), or at the collect before the start (Service.no_show_at_collect, core 0.2.7; `at` names the logged
        row). A side is absent if any of its seats has not started. With two or more sides and at least one side
        present, every absent side loses ("no_show", a valid forfeit): with two sides the present side wins; with more,
        an absent side retires if the sport lets the others play on (Match.retire), else the match ends there. If no
        side is present the match is incomplete (a technical failure, no winner). A single-side format (whose window
        opens when the service starts) is a valid loss ("no_show", success 0). True = the match goes on with the
        present sides, who have all started."""
        absent = self.absent_sides()
        present = [x for x in self.active_sides() if x not in absent]
        self.ep.write(at, started={s: st.joined for s, st in self.seats.items()}, absent=absent)
        if not absent:
            return True
        if len(self.cfg.side_list()) == 1:          # a single player (or team) who never started: a valid loss
            self.lose(next(s for s in self.cfg.seats if not self.seats[s].joined), "no_show")
            return False
        if not present:
            self.end("incomplete")
            return False
        for side in absent:
            seat = next(s for s in self.cfg.seats_of(side) if not self.seats[s].joined)
            if not self.lose(seat, "no_show"):
                return False
        return True

    def no_show_at_collect(self) -> bool:
        """With the lock held, at the collect (every player session has ended) before the match has started: the
        session end is a no-show, decided at once instead of when the start window closes (core rule 5,
        docs/framework_zh.md §9; core 0.2.7). Every side that has not started loses ("no_show", a valid forfeit;
        Service.close_start_window): a single side (alone or against a scripted opponent) has a valid loss (success 0);
        with two sides the present side wins; with more, the absent sides retire or the match ends as at the window.
        If no side has started (with two or more sides) nothing is decided here: the match does not count, as before
        (the caller ends it unfinished). True = the match ended; False = not before the start, no side present, or
        present sides would play on (more than two sides; the caller ends the match unfinished)."""
        if self.phase != "prepare" or self.in_play():
            return False
        if len(self.cfg.side_list()) > 1 and not [x for x in self.active_sides() if x not in self.absent_sides()]:
            return False
        return not self.close_start_window("collect_before_start")

    def in_play(self) -> bool:
        """With the lock held: the match has started (play has begun, or every seat has started and play is about to
        begin) and is not over."""
        if self.phase == "prepare":
            return all(st.joined for st in self.seats.values())
        return self.phase != "over"

    def abandon_single(self) -> bool:
        """With the lock held, at the collect (the verifier collects once every player session has ended): a single
        side (alone or against a scripted opponent) whose match has started and is not over loses, "abandoned", a
        valid loss (success 0), in both protocols (core rule 6, docs/framework_zh.md §9; core 0.2.6). Ending the
        session early (the player thinks it is done, gives up, hits the agent time limit or runs out of context) is the
        player's own problem; API and infrastructure failures are Harbor agent errors, rerun, not handled here. Before
        the start the session end is a no-show (Service.no_show_at_collect, core rule 5, core 0.2.7). True = the side
        lost."""
        # robot_coding_bench (board 0146, 2026-10-16): a built-in seat (RO_BUILTIN_SEATS, core/builtin_seat.py) never ends
        # a session, so a duel against one is a single side here: the HTTP side that leaves after the start loses
        # "abandoned", as against a scripted opponent (before: "collected", an unfinished match, not a valid trial).
        from .builtin_seat import parse as builtin_parse
        builtin = set(builtin_parse(os.environ.get("RO_BUILTIN_SEATS")))
        played = [s for s in self.cfg.seats if s not in builtin]
        if not played or len({self.cfg.side_of(s) for s in played}) != 1 or not self.in_play():
            return False
        self.lose(played[0], "abandoned")
        return True

    def end(self, reason, forfeiting=None):
        with self.cond:
            if self.finalizing:
                return
            if forfeiting is not None:
                self.forfeit(forfeiting, reason)
            self.on_end()
            self.phase, self.reason, self.finalizing = "over", reason, True
            self.ep.write("end", k=self.m.k, reason=reason)
            self.bc.frame(force=True)
            self.bc.event("end", reason=reason)
            self.cond.notify_all()
        threading.Thread(target=self.finalize, daemon=True).start()

    def on_end(self):
        pass

    def finalize(self):
        try:
            if not verdict_replay():         # live grading (robot_coding_bench, owner 2026-10-17): no replay
                raise _NoReplay
            subprocess.run([sys.executable, "-m", "core.episode", self.plugin, str(self.data)], check=True,
                           timeout=float(os.environ.get("RO_REPLAY_TIMEOUT_S", "600")), cwd=ROOT.parent,
                           stdout=subprocess.DEVNULL)
            self.replay = json.loads((self.data / "replay_check.json").read_text())
        except _NoReplay:
            pass
        except Exception as exc:  # noqa: BLE001
            self.errors.append({"where": "replay", "error": str(exc)[:300]})
        with self.cond:
            self.finalized = True
            self.write_final()
            self.cond.notify_all()
        for w in self.workers.values():
            busy = w.lock.acquire(timeout=60)    # a reply image may still be drawn after the last action
            w.close()
            if busy:
                w.lock.release()
        if os.environ.get("RCB_RENDER_VIDEO", "0") == "1":      # after graded-ready: spectators only, never an error
            try:
                subprocess.run([sys.executable, "-m", "core.spectator", self.plugin, str(self.data)], check=True,
                               timeout=float(os.environ.get("RCB_VIDEO_TIMEOUT_S", "300")), cwd=ROOT.parent,
                               stdout=subprocess.DEVNULL)
                self.video_info = json.loads((self.data / "video.json").read_text())
            except Exception as exc:  # noqa: BLE001
                self.video_info = {"video": False, "why": str(exc)[:200]}
            with self.cond:
                self.write_final()

    def outcome(self):
        return decide(self.m, self.forfeiting, self.reason, self.cfg.side_list(), self.cfg.side_of, self.retired)

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
        idx = os.environ.get("RO_SEED_INDEX", "")
        return {"commitment": self.hidden["commitment"], "index": int(idx) if idx.lstrip("-").isdigit() else None}

    def write_final(self):
        with self.cond:
            out = self.outcome()
            sha, cmds = self.m.state_digest(), self.ep.commands_sha()
            r = self.replay
            replay_ok = bool(r and r.get("state_sha") == sha and r.get("scores") == self.m.scores()
                             and r.get("winner") == out.winner and r.get("commands_sha") == cmds
                             and r.get("source_sha") == self.source_sha and r.get("k") == self.m.k)
            v = validity_fields(self.seats, self.need_meter)
            single = len(self.cfg.side_list()) == 1
            complete = self.reason == "match_over" or (self.reason in FORFEIT_REASONS and
                                                       (out.winner is not None or single))
            live = not verdict_replay()      # live grading: the verdict is this record's, no replay agreement
            valid = bool(self.finalized and complete and (replay_ok or live) and not self.errors
                         and not any(v["meter_error"].values()) and not any(v["proxy_error"].values()))
            cont = self.continuous()
            valid = valid and not self.errors
            sport = self.m.final_fields()
            seats = {s: dict(st.stats) for s, st in self.seats.items()}
            for s, extra in (sport.pop("seats", None) or {}).items():
                seats.setdefault(s, {}).update(extra)
            final = {"sport": self.sport.name, "protocol": self.protocol, "revision": self.sport.revision,
                     "versions": self.versions, "source_sha": self.source_sha, "cfg": self.cfg_json(),
                     "seed": self.cfg_json()["seed"], "first": self.cfg.first, "action_level": self.cfg.action_level,
                     "play": self.cfg.play, "format": self.cfg.format,
                     "sides": {s: self.cfg.side_of(s) for s in self.cfg.seats}, "phase": self.phase,
                     "reason": self.reason, "forfeiting": self.forfeiting, "retired": list(self.retired),
                     "scores": self.m.scores(), "match_winner": out.winner, "decided_by": out.decided_by,
                     "ranking": out.ranking, "solo": out.solo,
                     "winner": out.winner if valid else None, "state_sha": sha, "commands_sha": cmds,
                     "steps": self.m.k, "deterministic": None if live else replay_ok, "replay_scores": r.get("scores"),
                     "verdict_replay": not live,
                     "finalized": self.finalized, "graded_ready": self.finalized, "valid_trial": valid,
                     "technical_failure": not valid, "errors": self.errors, "seats": seats,
                     "joined": {s: st.joined for s, st in self.seats.items()}, "reviews": self.reviews,
                     "renderer": self.renderer_used(), "team_messages": len(self.channel.log),
                     "video": bool(self.video_info.get("video")), "video_info": self.video_info, "elapsed_s": round(time.monotonic() - self.t0, 1), **v, **self.extra_final(),
                     "continuous": cont, "seed_proof": self.seed_proof(),
                     "sport_fields": sport}
            if live:                             # the protocol's own fields (board 0151): graded by the live match
                final.update(graded_by="live", replays=0)
            compat = {k: v for k, v in sport.items() if k not in final}     # see COMPAT below
            if "score" not in final and "score" not in compat:
                compat["score"] = final["scores"]
            final.update(compat)
            final["compat"] = {"schema": COMPAT, "lifted": sorted(compat)}
            tmp = self.data / "final.json.tmp"
            if self.hidden:                      # the sport's fields (a sport may record its seed): scrubbed
                for k in {"sport_fields", "seats", "video_info", "errors", *compat}:
                    if k in final:
                        final[k] = self.public(final[k])
            tmp.write_text(json.dumps(final, default=float))
            tmp.replace(self.data / "final.json")

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

    def spec(self, seat, body=None):
        out = {"seat": seat, "side": self.cfg.side_of(seat), "protocol": self.protocol_id,
               "revision": self.sport.revision, "versions": self.versions, "action_level": self.cfg.action_level,
               "play": self.cfg.play, "format": self.cfg.format, **self.spec_core(),
               **public_spec(self.sport, self.cfg, seat, self.m, self.layer, self.decl)}
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
