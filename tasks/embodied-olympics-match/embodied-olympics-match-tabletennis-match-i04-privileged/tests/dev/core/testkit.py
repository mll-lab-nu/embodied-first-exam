"""The generic test suite every sport passes (tools/check stages 2 and 4; docs/framework_zh.md §9 sport rules). It
loads the sport like the core does and plays in-process matches of the sport's built-in players (core/local.py).

    python3 -m core.testkit tests    PLUGIN [--json OUT]     stage 2: the generic tests + the sport's exploit tests
    python3 -m core.testkit fairness PLUGIN [--json OUT]     stage 4: first-order and seat advantage of built-ins

Tests (each one result row {name, ok, detail}):
  determinism        the same match twice in-process gives the same digest; its episode replays in a fresh process
                     (python -m core.episode) to the same digest, scores and winner, within replay_timeout(decl)
                     (core 0.2.17: sport.toml [timing] replay_timeout_s when it is above 1800 s, else 1800 s)
  no_draw            every finished match of every format with two or more sides has a winner; the tiebreak names
                     are sport.toml [tiebreaks] order
  mirror_symmetry    sport.toml [fairness] mirror = "exact": swapping seats and the first order swaps the result and
                     a player sees exactly the same observations
  whitelist          no observation field outside sport.toml [observation] fields in any match; the core drops an
                     injected field and records the error
  observe_is_pure    observe / cameras / render_state / reply_views never change the state digest
  refuses_bad        malformed or out-of-range actions are refused (HTTP 400) and change nothing
  fuzz_actions       every format and action level: hostile bodies (huge integers, NaN / inf, wrong types, nested
                     junk, oversize strings and lists) through the core's parse_action are refused, raise nothing but
                     Refused and change nothing; junk observation queries change nothing (core 0.2.11)
  frame_budget       the task renderer draws one observation within [observation] frame_budget_ms; a sport with
                     reply images (Match.reply_views) also draws the first action's reply image within it
  exploit:<id>       every [[exploits]] entry names a test in tests/test_*.py, and that test passes
  solo_quit          every single-side format: a session that ends mid-match (the core's forfeit "abandoned" after
                     some play, core 0.2.6) is a loss with no winner, and its episode replays in a fresh process to the
                     same digest and decision
  prestart_no_show   every format of one or two sides: a side that never started (the core's forfeit "no_show" at
                     step 0, at the start window or at a collect before the start, core 0.2.7) replays to a loss: no
                     winner for a single side, the other side's win in a duel, with no play (k = 0); the sport's
                     forfeit hook may end its world (core 0.2.12: the core decides a forfeit first, whatever the phase)
  seed_private       information (core 0.2.14): where the sport itself shows the seed (observe, /spec, final fields);
                     the core scrubs them in hidden-seed matches
  continuous_score   sport.toml [score] (core 0.2.14): well formed; the values of every no_draw match are finite, within
                     its range and not below the forfeit value; a side that never started gets the forfeit value
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

from . import local
from . import score as score_mod
from . import spec as spec_mod
from .episode import load_plugin
from .observe import filter_fields, players_scene
from .service import own_hook
from .sport import FINISHED, MatchConfig, Refused, check_body, parse_action

ROOT = Path(__file__).resolve().parent
REPLAY_TIMEOUT_S = 1800     # the fresh-process replay of a test match, unless the sport declares a longer one


def replay_timeout(decl) -> float:
    """The limit of the tests' fresh-process replays (determinism, solo_quit), core 0.2.17: sport.toml [timing]
    replay_timeout_s when it is longer than REPLAY_TIMEOUT_S (a long match, e.g. 600 s of play, replays in more than
    1800 s), else REPLAY_TIMEOUT_S. Never shorter than the 1800 s of cores <= 0.2.16: the task's own limit (default
    600 s, tools/sportlib.py post_match_timeouts) does not tighten the check."""
    t = (decl.get("timing") or {}).get("replay_timeout_s")
    return max(float(REPLAY_TIMEOUT_S), float(t)) if t else float(REPLAY_TIMEOUT_S)


def fresh_replay(plugin, data, decl) -> tuple[dict, str]:
    """Replay the episode in `data` in a fresh process (python -m core.episode): (replay_check.json or {}, stderr)."""
    limit = replay_timeout(decl)
    try:
        p = subprocess.run([sys.executable, "-m", "core.episode", plugin, data], cwd=ROOT.parent,
                           capture_output=True, text=True, timeout=limit)
    except subprocess.TimeoutExpired:
        return {}, f"the fresh-process replay took more than {limit:.0f} s (sport.toml [timing] replay_timeout_s)"
    return (json.loads((Path(data) / "replay_check.json").read_text()) if p.returncode == 0 else {}), p.stderr


def configs(decl, sport, seeds=(1, 2, 3)):
    """One MatchConfig per (format, action level, seed, first side) the sport declares."""
    levels = (decl.get("modes") or {}).get("action_levels", ["high"])
    for fmt, f in (decl.get("formats") or {}).items():
        firsts = f.get("first") or [f["seats"][0]]
        for level in levels:
            for seed in seeds:
                for first in firsts:
                    yield MatchConfig(sport=sport.name, format=fmt, seats=tuple(f["seats"]), seed=seed, first=first,
                                      action_level=level, sides=f.get("sides"))


class Recorder:
    """Wraps a built-in player and keeps what it saw (the state part of each view)."""

    def __init__(self, inner):
        self.inner, self.seen = inner, []

    def act(self, view):
        self.seen.append({k: v for k, v in view["state"].items() if k != "seat"})
        return self.inner.act(view)


def row(name, ok, detail=""):
    return {"name": name, "ok": bool(ok), "detail": detail if isinstance(detail, str) else json.dumps(detail)[:600]}


def t_determinism(sport, plugin, decl):
    out = []
    cfg = next(configs(decl, sport, seeds=(7,)))
    names = {s: "reference" for s in cfg.seats}
    with tempfile.TemporaryDirectory() as tmp:
        a = local.play(sport, cfg, local.make_players(sport, cfg, names, plugin=plugin), data=tmp, plugin=plugin)
        b = local.play(sport, cfg, local.make_players(sport, cfg, names, plugin=plugin), plugin=plugin)
        out.append(row("determinism:in_process", a["digest"] == b["digest"] and a["scores"] == b["scores"],
                       {"a": a["digest"][:16], "b": b["digest"][:16]}))
        rc, err = fresh_replay(plugin, tmp, decl)
        ok = rc.get("state_sha") == a["digest"] and rc.get("scores") == a["scores"] and rc.get("winner") == a["winner"]
        out.append(row("determinism:fresh_process_replay", ok, rc and {k: rc[k] for k in ("scores", "winner", "k")}
                       or err[-400:]))
    return out


def t_no_draw_and_whitelist(sport, plugin, decl, n=4):
    order = (decl.get("tiebreaks") or {}).get("order")
    bad, leaks, played, names_ok, cont = [], set(), 0, True, []
    checks = (decl.get("players") or {}).get("check", ["random"])
    for cfg in configs(decl, sport, seeds=tuple(range(1, n + 1))):
        for pol in checks + ["reference"]:
            names = {s: (pol if i % 2 == 0 else "reference") for i, s in enumerate(cfg.seats)}
            r = local.play(sport, cfg, local.make_players(sport, cfg, names, plugin=plugin), plugin=plugin)
            played += 1
            leaks |= set(r["observation_leaks"])
            if r.get("continuous"):
                cont.append(r["continuous"]["by_side"])
            if len(cfg.side_list()) >= 2 and r["finished"] and r["winner"] is None:
                bad.append({"cfg": cfg.to_json(), "scores": r["scores"]})
            if not r["finished"]:
                bad.append({"cfg": cfg.to_json(), "unfinished": True})
        m = sport.build(cfg)
        if order is not None and len(cfg.side_list()) >= 2 and [x for x, _ in m.tiebreaks()] != order:
            names_ok = False
    out = [row("no_draw", not bad, bad[:3] or f"{played} matches, every one decided"),
           row("tiebreaks_declared", names_ok and order is not None or not any(
               len(f["seats"]) > 1 for f in decl.get("formats", {}).values()),
               f"sport.toml [tiebreaks] order = {order}"),
           row("whitelist:no_leak", not leaks, sorted(leaks) or "every observation within the whitelist")]
    sd = score_mod.declaration(decl)
    if sd is not None:
        vals = [v for by in cont for v in by.values()]
        lo, hi = (sd.get("range") or [-math.inf, math.inf])
        out.append(row("continuous_score:values", vals and all(lo <= v <= hi for v in vals)
                       and all(sd["forfeit"] <= v for v in vals),
                       f"{len(vals)} values in [{min(vals, default=None)}, {max(vals, default=None)}], range "
                       f"{sd.get('range')}, forfeit {sd['forfeit']} (must be the worst)"))
    cfg = next(configs(decl, sport))
    m = sport.build(cfg)
    allowed = spec_mod.whitelist(decl)
    obs = dict(m.observe(cfg.seats[0], None), _secret_state=[1, 2, 3])
    kept, dropped = filter_fields(obs, allowed)
    out.append(row("whitelist:declared", allowed is not None, "sport.toml [observation] fields"))
    out.append(row("whitelist:enforced", "_secret_state" not in kept and dropped == ["_secret_state"], dropped))
    return out


def t_mirror(sport, plugin, decl, seeds=(1, 2, 3, 4)):
    if (decl.get("fairness") or {}).get("mirror") != "exact":
        return [row("mirror_symmetry", True, "skipped: [fairness] mirror is not \"exact\" (the fairness check covers it)")]
    out = []
    for fmt, f in decl.get("formats", {}).items():
        seats = f["seats"]
        if len(seats) != 2:
            continue
        for level in (decl.get("modes") or {}).get("action_levels", ["high"]):
            for seed in seeds:
                res = []
                for swap in (False, True):
                    cfg = MatchConfig(sport=sport.name, format=fmt, seats=tuple(seats), seed=seed,
                                      first=seats[1] if swap else seats[0], action_level=level)
                    pol = ["reference", "random"][::-1] if swap else ["reference", "random"]
                    ps = {s: Recorder(local.make_players(sport, cfg, {s: n}, plugin=plugin, seed=seed)[s])
                          for s, n in zip(seats, pol)}
                    r = local.play(sport, cfg, ps, plugin=plugin)
                    res.append((r, ps))
                (r1, p1), (r2, p2) = res
                a, b = seats
                swapped = r1["scores"] == {a: r2["scores"][b], b: r2["scores"][a]} and \
                    ({a: b, b: a}.get(r1["winner"]) == r2["winner"])
                same_view = p1[a].seen == p2[b].seen and p1[b].seen == p2[a].seen
                out.append(row(f"mirror_symmetry:{fmt}:{level}:seed{seed}", swapped and same_view,
                               {"scores": [r1["scores"], r2["scores"]], "same_observations": same_view}))
    return out or [row("mirror_symmetry", True, "no two-seat format")]


def t_pure(sport, plugin, decl):
    cfg = next(c for c in configs(decl, sport) if len(c.seats) >= 1)
    m = sport.build(cfg)
    ps = local.make_players(sport, cfg, {s: "reference" for s in cfg.seats}, plugin=plugin)
    layer = sport.action_layer(cfg.action_level)
    views = local.Views(sport, cfg, m, decl, True, plugin)
    bad = []
    for _ in range(4):
        if m.phase().state == FINISHED:
            break
        seat = m.to_move() or cfg.seats[0]
        d0 = m.state_digest()
        for s in cfg.seats:
            m.observe(s, None)
            m.cameras(s, None)
        m.render_state()
        v = views.view(seat, {})
        if m.state_digest() != d0:
            bad.append("observe/cameras/render_state changed the digest")
        if sport.protocol == "turn":
            low, _ = layer.lower(seat, layer.parse(seat, ps[seat].act(v), m, {"clock_left_s": {}}), None, m)
            info = m.apply(seat, low) or {}
            d1 = m.state_digest()
            m.reply_views(seat, low, info)
            if m.state_digest() != d1:
                bad.append("reply_views changed the digest")
        else:
            m.step()
    return [row("observe_is_pure", not bad, bad or "digest unchanged by observations")]


def bad_bodies(schema: dict):
    kind, fields = next(iter(schema.items()))
    good = {k: (f.get("min", 0) + f.get("max", 0)) / 2 if f.get("type", "number") == "number" else f.get("default")
            for k, f in fields.items()}
    yield {"type": "no-such-action"}
    yield {"type": kind}
    for k, f in fields.items():
        if f.get("type", "number") in ("number", "integer"):
            for v in (float("nan"), "1", f.get("max", 1e9) + 1e6 if "max" in f else None):
                if v is not None:
                    yield {"type": kind, **good, k: v}
    yield {"type": kind, **good, "unexpected_field": 1}


def t_refuses(sport, plugin, decl):
    out = []
    for level in (decl.get("modes") or {}).get("action_levels", ["high"]):
        cfg = next(c for c in configs(decl, sport) if c.action_level == level)
        m = sport.build(cfg)
        layer = sport.action_layer(level)
        seat = m.to_move() or cfg.seats[0]
        schema = layer.schema(m, seat) if hasattr(layer, "schema") else {}
        if not schema:
            out.append(row(f"refuses_bad:{level}", True, "skipped: the layer publishes no schema"))
            continue
        d0, leaked = m.state_digest(), []
        for body in bad_bodies(schema):
            try:
                layer.parse(seat, body, m, {"clock_left_s": {}})
                leaked.append(body)
            except Refused:
                pass
        out.append(row(f"refuses_bad:{level}", not leaked and m.state_digest() == d0,
                       [str(b) for b in leaked][:3] or "every malformed action refused, nothing changed"))
    return out


FUZZ_ALWAYS_BAD = {                     # the core refuses these in any field of any action (core 0.2.11)
    "inf": float("inf"), "-inf": float("-inf"), "nan": float("nan"), "hugeint": 10 ** 400, "-hugeint": -10 ** 400,
    "int2^70": 2 ** 70, "1e300": 1e300, "deep": json.loads("[" * 30 + "]" * 30), "longstr": "x" * 20000,
    "longlist": [0.1] * 5000}
FUZZ_WRONG_TYPE = {"null": None, "true": True, "str": "x", "list": [1, 2, 3], "nested": [[1], [2]], "dict": {"a": 1},
                   "empty_list": [], "dict_nested": {"a": {"b": [1, {"c": None}]}}}
FUZZ_QUERIES = ({"camera": float("inf")}, {"camera": {"a": 1}}, {"camera": 10 ** 400}, {"aim": "x"}, {"aim": [1]},
                {"x": [[1]]}, {"view": None}, {"camera": "x" * 5000})


def fuzz_bodies(schema: dict):
    """(name, body, must_refuse): malformed act bodies for every action type and field of a layer's schema."""
    for junk in ([], "x", 5, None, [{"type": "x"}]):
        yield f"body={junk!r}", junk, True
    for v in (None, [], {}, ["x"], 10 ** 400, float("nan"), "x" * 5000, True, 3):
        yield f"type={str(v)[:12]}", {"type": v}, v is not None
    for kind, fields in (schema or {}).items():
        fields = fields if isinstance(fields, dict) else {}
        good = {}
        for k, f in fields.items():
            f = f if isinstance(f, dict) else {}
            if f.get("type", "number") in ("number", "integer"):
                lo, hi = f.get("min", 0), f.get("max", 0)
                good[k] = (lo + hi) / 2 if all(isinstance(x, (int, float)) for x in (lo, hi)) else 0
            elif "default" in f:
                good[k] = f["default"]
        for k in [*fields, "type", "entity", "unexpected_field"]:
            for name, v in FUZZ_ALWAYS_BAD.items():
                yield f"{kind}.{k}={name}", {"type": kind, **good, k: v}, True
            for name, v in FUZZ_WRONG_TYPE.items():
                yield f"{kind}.{k}={name}", {"type": kind, **good, k: v}, k == "type" and v is not None


def t_fuzz(sport, plugin, decl):
    """Malformed actions and observation queries, through the core's own path (core.sport.parse_action, the same
    function the HTTP service runs): every always-bad body is refused, nothing raises anything but Refused, nothing
    changes the state digest. Every format and action level."""
    out, seen = [], set()
    for cfg in configs(decl, sport, seeds=(1,)):
        if (cfg.format, cfg.action_level) in seen:
            continue
        seen.add((cfg.format, cfg.action_level))
        m = sport.build(cfg)
        layer = sport.action_layer(cfg.action_level)
        seat = m.to_move() or cfg.seats[0]
        schema = layer.schema(m, seat) if hasattr(layer, "schema") else {}
        d0, bad, n = m.state_digest(), [], 0
        for name, body, must in fuzz_bodies(schema):
            n += 1
            try:
                parse_action(layer, seat, body, m, {"clock_left_s": {s: 600.0 for s in cfg.seats}})
                if must:
                    bad.append(f"{name}: accepted")
            except Refused:
                pass
            except Exception as exc:  # noqa: BLE001
                bad.append(f"{name}: {type(exc).__name__} escaped parse_action")
        for q in FUZZ_QUERIES:            # the core: check_body, then any exception with a query is a refusal
            n += 1
            try:
                check_body({"query": q})
                m.observe(seat, q)
                m.cameras(seat, q)
            except Exception:  # noqa: BLE001
                pass
        if m.state_digest() != d0:
            bad.append("the state digest changed")
        out.append(row(f"fuzz_actions:{cfg.format}:{cfg.action_level}", not bad,
                       bad[:4] or f"{n} malformed bodies and queries refused, nothing changed"))
    return out


def t_budget(sport, plugin, decl):
    obs = decl.get("observation") or {}
    budget = obs.get("frame_budget_ms")
    cfg = next(configs(decl, sport))
    m = sport.build(cfg)
    pres = Path(plugin).resolve().parent / "presentation"
    players = None
    if (pres / "presentation.toml").is_file():
        from renderers import presentation
        players = presentation.players_meshes(pres)
    if not own_hook(m, "cameras") or own_hook(m, "camera_job"):
        if players is None:
            return [row("frame_budget", True, "skipped: the sport draws its own images (a wrapper)")]
        return [_own_budget(sport, cfg, m, decl, plugin, budget, players)]
    from renderers import budget as B
    import renderers
    from renderers.base import CameraDef
    name = obs.get("renderer") or renderers.DEFAULT
    cams = [CameraDef.from_dict(c) for c in m.cameras(cfg.seats[0], None)]
    ok, ms = B.check_budget(renderers.load(name), players_scene(sport, plugin, cfg), m.render_state(), cams,
                            budget_ms=budget or 1e9)
    what = f", players' presentation scene ({players} meshes)" if players else ""
    out = [row("frame_budget", budget is not None and ok,
               f"{name}{what}: {ms:.1f} ms per observation, budget {budget} ms")]
    if own_hook(m, "reply_views"):
        out.append(t_reply_budget(sport, plugin, decl, cfg, name, budget))
    return out


def t_reply_budget(sport, plugin, decl, cfg, name, budget):
    """The first action's reply image (Match.reply_views, core 0.2.8), drawn as the service draws it (the core's
    camera worker), within [observation] frame_budget_ms (median of 3 after one warm-up)."""
    from .observe import CameraWorker, reply_job
    m = sport.build(cfg)
    layer = sport.action_layer(cfg.action_level)
    ps = local.make_players(sport, cfg, {s: "reference" for s in cfg.seats}, plugin=plugin)
    views = local.Views(sport, cfg, m, decl, True, plugin)
    job = None
    for _ in range(50):                       # the first action that has reply images
        if m.phase().state == FINISHED:
            break
        seat = m.to_move() or cfg.seats[0]
        if sport.protocol != "turn":
            m.step()
            continue
        low, _ = layer.lower(seat, layer.parse(seat, ps[seat].act(views.view(seat, {})), m, {"clock_left_s": {}}),
                             None, m)
        info = m.apply(seat, low) or {}
        job = reply_job(m, m.reply_views(seat, low, info), int((decl.get("observation") or {}).get("columns", 2)))
        if job is not None:
            break
    if job is None:
        return row("reply_budget", False, "Match.reply_views gave no image for the first actions of the reference")
    w = CameraWorker(players_scene(sport, plugin, cfg), name)
    w.draw_job(job)
    times = []
    for _ in range(3):
        t = time.perf_counter()
        img = w.draw_job(job)
        times.append((time.perf_counter() - t) * 1000.0)
    ms = sorted(times)[1]
    ok = budget is not None and ms <= float(budget)
    return row("reply_budget", ok, f"{name}: {ms:.1f} ms per reply image ({len(img['tiles'])} tiles), budget {budget} ms")


def _own_budget(sport, cfg, m, decl, plugin, budget, players, n: int = 5, between: int = 30):
    """A sport that draws its own images from its players' presentation scene: the median wall time of its own
    observation path (Views.view) from a fresh world, `between` control steps apart early in play (a realtime world
    may freeze between rallies: only observations whose image changed count), after a warm-up."""
    m = sport.build(cfg)
    views = local.Views(sport, cfg, m, decl, True, plugin)
    seat = cfg.seats[0]

    def run(k):
        if sport.protocol == "realtime":
            for _ in range(k):
                if m.phase().state == FINISHED:
                    break
                m.step()
    last = views.view(seat, {})["observation"].get("image_png_b64")
    times, tries = [], 0
    while len(times) < n and tries < 4 * n:
        tries += 1
        run(between)
        t = time.perf_counter()
        img = views.view(seat, {})["observation"].get("image_png_b64")
        ms = (time.perf_counter() - t) * 1000.0
        if img != last or sport.protocol != "realtime":
            times.append(ms)
        last = img
    if not times:
        return row("frame_budget", False, "no observation with a new image to time")
    ms = sorted(times)[len(times) // 2]
    return row("frame_budget", budget is not None and ms <= float(budget),
               f"the sport's own images from its players' presentation scene ({players} meshes): {ms:.1f} ms per "
               f"observation (median of {len(times)} with a new image), budget {budget} ms")


def t_exploits(sport, plugin, decl):
    out = []
    tests_dir = Path(plugin).parent / "tests"
    funcs = {}
    for p in sorted(tests_dir.glob("test_*.py")):
        spec = importlib.util.spec_from_file_location(f"sport_test_{p.stem}", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        funcs.update({k: v for k, v in vars(mod).items() if k.startswith("test_") and callable(v)})
    for ex in decl.get("exploits", []):
        f = funcs.get(ex.get("test", ""))
        if f is None:
            out.append(row(f"exploit:{ex.get('id')}", False, f"no test {ex.get('test')!r} in tests/test_*.py"))
            continue
        try:
            f()
            out.append(row(f"exploit:{ex['id']}", True, ex.get("text", "")))
        except Exception:  # noqa: BLE001
            out.append(row(f"exploit:{ex['id']}", False, traceback.format_exc()[-500:]))
    if not decl.get("exploits"):
        out.append(row("exploit_list", False, "sport.toml has no [[exploits]]"))
    return out


class Idle:
    """A built-in player that never acts (the realtime world runs on without it)."""

    def act(self, view):
        return None


def t_solo_quit(sport, plugin, decl, steps=40):
    """core 0.2.6 (core rule 6): the collect of a started single-side match writes a forfeit row "abandoned" at the
    current step; the sport's forfeit hook and the fresh-process replay must agree on a loss without a winner."""
    from .episode import read_rows, replay
    out = []
    for fmt, f in (decl.get("formats") or {}).items():
        if len({(f.get("sides") or {}).get(s, s) for s in f["seats"]}) != 1:
            continue
        cfg = next(c for c in configs(decl, sport, seeds=(1,)) if c.format == fmt)
        with tempfile.TemporaryDirectory() as tmp:
            r = local.play(sport, cfg, {s: Idle() for s in cfg.seats}, data=tmp, render=False, plugin=plugin,
                           max_actions=0, max_steps=steps)
            ep = Path(tmp) / "episode.jsonl"
            rows = [x for x in read_rows(ep) if x["ev"] != "end"]
            rows += [{"ev": "forfeit", "k": r["k"], "seat": cfg.seats[0], "why": "abandoned"},
                     {"ev": "end", "k": r["k"], "reason": "abandoned"}]
            ep.write_text("".join(json.dumps(x, default=float) + "\n" for x in rows))
            mine = replay(sport, rows)
            rc, err = fresh_replay(plugin, tmp, decl)
        ok = (not r["finished"] and mine["winner"] is None and mine["decided_by"] == "forfeit:abandoned"
              and rc.get("state_sha") == mine["state_sha"] and rc.get("winner") is None
              and rc.get("decided_by") == "forfeit:abandoned" and rc.get("k") == r["k"])
        out.append(row(f"solo_quit:{fmt}", ok, {"k": r["k"], "finished_before": r["finished"],
                                                "decided_by": mine["decided_by"], "replay": rc.get("decided_by")}
                       if rc else err[-400:]))
    return out


def t_prestart_no_show(sport, plugin, decl):
    """core 0.2.7 (core rule 5): a side that never started loses before any play ("no_show" at step 0, when the start
    window closes or at a collect before the start). For every format of one or two sides, the episode the core then
    writes (header, the forfeit row of the first seat of the last side, end) must replay to that decision: a single
    side's loss without a winner, or the other side's win, at step 0. Whether the world then reports itself finished
    is the sport's own business (Match.forfeit records the decision inside the world; a sport may end it there,
    game over, winner set): the core decides a forfeit before it looks at the phase (core.outcome.decide), and the
    service's validity reads the end reason, not the phase (core 0.2.12)."""
    from .episode import replay
    out = []
    for fmt, f in (decl.get("formats") or {}).items():
        cfg = next(c for c in configs(decl, sport, seeds=(1,)) if c.format == fmt)
        sides = list(cfg.side_list())
        if len(sides) > 2:
            continue
        seat = next(s for s in cfg.seats if cfg.side_of(s) == sides[-1])
        rows = [{"ev": "header", "cfg": cfg.to_json(), "sport": sport.name, "protocol": sport.protocol},
                {"ev": "forfeit", "k": 0, "seat": seat, "why": "no_show"}, {"ev": "end", "k": 0, "reason": "no_show"}]
        r = replay(sport, rows)
        want = sides[0] if len(sides) == 2 else None
        ok = r["winner"] == want and r["decided_by"] == "forfeit:no_show" and r["k"] == 0
        out.append(row(f"prestart_no_show:{fmt}", ok, {"absent": seat, "winner": r["winner"], "want": want,
                                                        "decided_by": r["decided_by"], "k": r["k"],
                                                        "finished": r["finished"]}))
    return out


def t_continuous(sport, plugin, decl):
    """core 0.2.14 (sport.toml [score], core/score.py): the declaration is well formed, and a side that never started
    gets the forfeit value while the other side's value is a finite number (the definition copes with no play)."""
    from .episode import replay
    sd = score_mod.declaration(decl)
    if sd is None:
        return [row("continuous_score", True, "not declared (sport.toml [score]); tools/check warns")]
    bad = score_mod.problems(decl, own_hook(sport.build(next(configs(decl, sport, seeds=(1,)))), "continuous_score"))
    out = [row("continuous_score:declared", not bad, "; ".join(bad) or f"{sd['name']} (from {sd['from']})")]
    for fmt, f in (decl.get("formats") or {}).items():
        cfg = next(c for c in configs(decl, sport, seeds=(1,)) if c.format == fmt)
        sides = list(cfg.side_list())
        if len(sides) > 2:
            continue
        seat = next(s for s in cfg.seats if cfg.side_of(s) == sides[-1])
        rows = [{"ev": "header", "cfg": cfg.to_json(), "sport": sport.name, "protocol": sport.protocol},
                {"ev": "forfeit", "k": 0, "seat": seat, "why": "no_show"}, {"ev": "end", "k": 0, "reason": "no_show"}]
        try:
            by = replay(sport, rows, decl=decl)["continuous"]
            ok = by[sides[-1]] == sd["forfeit"] and all(math.isfinite(v) for v in by.values())
        except Exception as exc:  # noqa: BLE001
            by, ok = f"{type(exc).__name__}: {exc}"[:300], False
        out.append(row(f"continuous_score:no_show:{fmt}", ok, {"by_side": by, "forfeit": sd["forfeit"]}))
    return out


def t_seed_private(sport, plugin, decl, seed=987123):
    """core 0.2.14 (core/seeds.py): where the sport itself shows a match's seed (observation, /spec, final fields). For
    information: in a hidden-seed match the core scrubs all three, but a sport should not show the seed at all."""
    import re
    cfg = next(configs(decl, sport, seeds=(seed,)))
    m = sport.build(cfg)
    pat = re.compile(rf"(?<![\d.]){seed}(?![\d.])|\"\w*seed\"")
    where = [name for name, fn in (("observe", lambda: [m.observe(s, None) for s in cfg.seats]),
                                   ("spec", lambda: local.seat_spec(sport, cfg, cfg.seats[0], m, plugin)),
                                   ("final_fields", m.final_fields))
             if pat.search(json.dumps(fn(), default=str))]
    return [row("seed_private", True, f"the sport shows the seed in {where} (scrubbed in hidden-seed matches)"
                if where else "the sport shows the seed nowhere")]


def tests(plugin):
    sport, decl = load_plugin(plugin), spec_mod.load(plugin)
    out = []
    for f in (t_determinism, t_no_draw_and_whitelist, t_mirror, t_pure, t_refuses, t_fuzz, t_budget, t_exploits,
              t_solo_quit, t_prestart_no_show, t_continuous, t_seed_private):
        t = time.time()
        try:
            rows = f(sport, plugin, decl)
        except Exception:  # noqa: BLE001
            rows = [row(f.__name__[2:], False, traceback.format_exc()[-800:])]
        for r in rows:
            r["s"] = round(time.time() - t, 1)
        out += rows
    return out


def advantage(wins: int, games: int, fair: float, lim: float) -> dict:
    """A side's (or a seat's) advantage in percentage points with its 95% confidence interval (normal approximation of
    the win rate). The rule (sport rule 6): FAIL only if the whole interval lies beyond +-lim (a real advantage);
    WARN if the interval is wider than +-lim (too few matches to tell)."""
    p = wins / games if games else fair
    adv = 100.0 * (p - fair)
    h = 196.0 * math.sqrt(max(p * (1 - p), 1e-9) / games) if games else 100.0
    return {"advantage_pp": round(adv, 2), "ci95_pp": round(h, 2), "lo": adv - h, "hi": adv + h,
            "fail": adv - h > lim or adv + h < -lim, "wide": h > lim}


def fairness(plugin, matches=None):
    """Built-in players on every seat, both first orders, N seeds each: the advantage of the side that starts and of the
    first seat, each with its 95% confidence interval (advantage()); the seeds are fixed, so the check is
    reproducible. A format plays with its declared sides, and the fair share is one over their number (core 0.2.13:
    a team format is two sides, not one side per seat). Turn-based sports (cheap to play) must also play enough
    matches: an interval wider than +-lim FAILS there; realtime sports only WARN (decided 2026-10-06). An explicit
    `matches` (tools/check --quick) only warns."""
    sport, decl = load_plugin(plugin), spec_mod.load(plugin)
    fc = decl.get("fairness") or {}
    pol, lim = fc.get("policy", "reference"), fc.get("max_advantage_pp", 5)
    n = int(matches or fc.get("matches_per_order", 100))
    out = []
    for fmt, f in decl.get("formats", {}).items():
        seats = f["seats"]
        if len(seats) < 2:
            continue
        level = (decl.get("modes") or {}).get("action_levels", ["high"])[0]
        firsts = f.get("first") or seats
        first_wins = seat_wins = games = 0
        for first in firsts:
            for seed in range(1, n + 1):
                cfg = MatchConfig(sport=sport.name, format=fmt, seats=tuple(seats), seed=seed, first=first,
                                  action_level=level, sides=f.get("sides"))
                r = local.play(sport, cfg, local.make_players(sport, cfg, {s: pol for s in seats}, plugin=plugin),
                               plugin=plugin)
                games += 1
                first_wins += r["winner"] == cfg.side_of(first)
                seat_wins += r["winner"] == cfg.side_of(seats[0])
        k = len(set(MatchConfig(sport.name, fmt, tuple(seats), 1, sides=f.get("sides")).side_list()))
        verdicts = {}
        for what, wins in (("first_side", first_wins), ("seat_" + seats[0], seat_wins)):
            verdicts[what] = advantage(wins, games, 1.0 / k, lim)
        wide = any(v["wide"] for v in verdicts.values())
        strict = sport.protocol == "turn" and matches is None
        fail = any(v["fail"] for v in verdicts.values()) or (strict and wide)
        warn = wide and not strict
        r = row(f"fairness:{fmt}", not fail, {"policy": pol, "N": games, "per_order": n, "max_pp": lim,
                                             **{w: {x: v[x] for x in ("advantage_pp", "ci95_pp")}
                                                for w, v in verdicts.items()}})
        r["warn"] = warn and not fail
        if r["warn"]:
            r["detail"] += f" -- WARN: the 95% CI is wider than +-{lim} pp; play more matches ([fairness] matches_per_order)"
        if strict and wide and not any(v["fail"] for v in verdicts.values()):
            r["detail"] += f" -- FAIL: turn-based sport, the 95% CI is wider than +-{lim} pp; raise [fairness] matches_per_order"
        out.append(r)
    return out or [row("fairness", True, "no format with two or more sides")]


def main(argv):
    cmd, plugin = argv[0], os.path.abspath(argv[1])
    res = tests(plugin) if cmd == "tests" else fairness(
        plugin, int(argv[argv.index("--matches") + 1]) if "--matches" in argv else None)
    if "--json" in argv:
        Path(argv[argv.index("--json") + 1]).write_text(json.dumps(res, indent=1))
    for r in res:
        print(f"{('WARN' if r.get('warn') else 'ok  ') if r['ok'] else 'FAIL'} {r['name']}: {r['detail']}")
    return 0 if all(r["ok"] for r in res) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
