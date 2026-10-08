"""In-process matches of built-in players (no HTTP, no wall clock): what the checks (tools/check) use for the generic
tests, the fairness check and golden recordings. The players see what they would see over HTTP (core/client.py: the
whitelisted observation with the camera images), the actions go through the same action layer, and the episode is the
same episode.jsonl the live service writes, so `python -m core.episode` replays it in a fresh process.

    play(sport, cfg, players, data=None, render=True) -> {"scores", "winner", "decided_by", "ranking", "k", "digest", ...}
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

from . import PROTOCOLS, VERSION
from . import spec as spec_mod
from .episode import Episode
from .observe import CameraWorker, filter_fields, players_scene
from .outcome import decide
from .service import own_hook, public_spec
from .sport import FINISHED, UNIT_OVER, Refused, parse_action

MAX_REFUSED = 50                # local play: a player whose actions keep being refused fails the match run

DEFAULT_CLOCK_S = 3600.0


class Views:
    """The view a player gets: {"state": core fields + the whitelisted observation, "observation": images}."""

    def __init__(self, sport, cfg, m, decl, render: bool, plugin: str | None = None):
        self.sport, self.cfg, self.m, self.render, self.plugin = sport, cfg, m, render, plugin
        self.allowed = spec_mod.whitelist(decl)
        self.columns = int((decl.get("observation") or {}).get("columns", 2))
        self.cam = None
        self.leaks: list[str] = []
        self.own_images = own_hook(m, "camera_job") or not own_hook(m, "cameras")

    def view(self, seat, extra: dict, query=None) -> dict:
        obs, bad = filter_fields(self.m.observe(seat, query), self.allowed)
        self.leaks += bad
        out = {"state": {"seat": seat, **extra, **obs}, "observation": {}}
        if not self.render:
            return out
        if self.own_images:
            job, meta = self.m.camera_job(seat)
            if job is not None:
                img = self.sport.worker_call(None, "render", job)
                out["observation"] = {"image_png_b64": base64.b64encode(img["png"]).decode(), **meta}
            return out
        cams = self.m.cameras(seat, query)
        if cams:
            if self.cam is None:
                scene = players_scene(self.sport, self.plugin, self.cfg) if self.plugin else self.sport.scene(self.cfg)
                self.cam = CameraWorker(scene, self.cfg.renderer)
            img = self.cam.draw(self.m.render_state(), cams, self.columns)
            out["observation"] = {"image_png_b64": base64.b64encode(img["png"]).decode(), "tiles": img["tiles"]}
        return out


def _header(ep, sport, cfg):
    if ep is not None:
        ep.write("header", cfg=cfg.to_json(), sport=sport.name, revision=sport.revision, protocol=sport.protocol,
                 source_sha=None, versions={"core": VERSION, "sport": sport.revision}, local=True)


def seat_spec(sport, cfg, seat, m=None, plugin=None) -> dict:
    """What GET /spec tells `seat` (without the protocol's timing part)."""
    decl = spec_mod.load(plugin) if plugin else {}
    m = m or sport.build(cfg)
    return {"seat": seat, "side": cfg.side_of(seat), "protocol": PROTOCOLS[sport.protocol], "revision": sport.revision,
            "action_level": cfg.action_level, "play": cfg.play, "format": cfg.format,
            **public_spec(sport, cfg, seat, m, sport.action_layer(cfg.action_level), decl)}


def make_players(sport, cfg, names: dict, plugin=None, seed=None) -> dict:
    """seat -> built-in player, by name (Sport.players())."""
    table = sport.players()
    return {s: table[n](seat_spec(sport, cfg, s, plugin=plugin), s, cfg.seed if seed is None else seed)
            for s, n in names.items()}


def play(sport, cfg, players: dict, data: Path | str | None = None, render: bool = True, plugin: str | None = None,
         max_actions: int = 10000, max_steps: int = 10 ** 7, every: int = 5) -> dict:
    """Play one match of built-in players (seat -> player). Turn protocol: the sport's to_move() decides who acts;
    realtime: every `every` control steps each seat may act; reviews end at once."""
    decl = spec_mod.load(plugin) if plugin else {}
    m = sport.build(cfg)
    layer = sport.action_layer(cfg.action_level)
    ep = None
    if data is not None:
        Path(data).mkdir(parents=True, exist_ok=True)
        (Path(data) / "episode.jsonl").unlink(missing_ok=True)
        ep = Episode(Path(data) / "episode.jsonl")
    _header(ep, sport, cfg)
    views = Views(sport, cfg, m, decl, render, plugin)
    clocks = {s: DEFAULT_CLOCK_S for s in cfg.seats}
    refused = {s: 0 for s in cfg.seats}
    log = (lambda ev, **row: ep.write(ev, **row)) if ep is not None else (lambda ev, **row: None)
    refused: dict = {}
    if sport.protocol == "turn":
        n = 0
        while m.phase().state != FINISHED and n < max_actions:
            seat = m.to_move()
            v = views.view(seat, {"phase": "play", "turn": "you", "your_turn": True, "done": False,
                                  "clock_left_s": clocks[seat]})
            body = players[seat].act(v)
            try:
                cmd = parse_action(layer, seat, body, m, {"clock_left_s": dict(clocks)})
            except Refused:                     # an invalid request is refused (HTTP 400 in a real match), not a crash
                refused[seat] = refused.get(seat, 0) + 1
                if refused[seat] > MAX_REFUSED:
                    raise RuntimeError(f"seat {seat}: more than {MAX_REFUSED} refused actions in local play")
                continue
            low, _info = layer.lower(seat, cmd, None, m)
            log("cmd", k=m.k, seat=seat, cmd=low)
            m.apply(seat, low)
            n += 1
    else:
        plan = {s: sport.worker_init("plan", s, cfg) for s in cfg.seats} if getattr(layer, "worker", None) else {}
        delay = int(getattr(layer, "delay_steps", 0) or 0)
        scheduled: list = []
        while m.phase().state != FINISHED and m.k < max_steps:
            if m.phase().state == UNIT_OVER:
                scheduled.clear()
                log("resume", k=m.k)
                m.resume()
            for item in [x for x in scheduled if x[0] <= m.k]:
                scheduled.remove(item)
                log("cmd", k=m.k, seat=item[1], cmd=item[2])
                m.apply(item[1], item[2])
            if m.k % every == 0:
                for seat in cfg.seats:
                    v = views.view(seat, {"phase": "running", "world": "running", "step": m.k,
                                          "t_sim": m.k * m.dt, "done": False})
                    body = players[seat].act(v)
                    if body is None:
                        continue
                    try:
                        cmd = parse_action(layer, seat, body, m, {})
                    except Refused:             # refused as in a real match (HTTP 400): the world goes on
                        refused[seat] = refused.get(seat, 0) + 1
                        continue
                    job = layer.snapshot(seat, cmd, m, m.k)
                    prepared = None
                    if job is not None:
                        prepared = (sport.worker_call(plan[seat], "plan", job) if plan else layer.prepare(job))
                    low, info = layer.lower(seat, cmd, prepared, m)
                    if delay:
                        scheduled.append((m.k + delay, seat, low))
                    else:
                        log("cmd", k=m.k, seat=seat, cmd=low)
                        if "rejected" in (m.apply(seat, low) or {}):
                            refused[seat] = refused.get(seat, 0) + 1
            m.step()
    finished = m.phase().state == FINISHED
    log("end", k=m.k, reason="match_over" if finished else "unfinished")
    out = decide(m, None, None, cfg.side_list(), cfg.side_of)
    res = {"scores": m.scores(), "winner": out.winner, "decided_by": out.decided_by, "ranking": out.ranking,
           "solo": out.solo, "k": m.k, "digest": m.state_digest(), "finished": finished,
           "observation_leaks": sorted(set(views.leaks)), "rejected": refused, "final_fields": m.final_fields()}
    if data is not None:
        (Path(data) / "local_result.json").write_text(json.dumps(res, default=float))
    return res
