"""The Judge: one Run's sealed evidence -> one verdict (eo-verdict/1). A pure function of the evidence, the frozen
rules (rules.py, the Task's validity declaration) and this code: no network, no machine state. Re-judging the same
evidence gives the same normalized verdict bytes (verdict_bytes: JCS without `meta`).

    from framework.judge import evidence, verdict
    v = verdict.judge(evidence.load(run_dir))

Steps: derive the facts (who played, how the match ended, what the world reported), check the inputs (checks.py),
collect the faults (each with its class, scope, effect and the rule that produced it), decide validity per the Task's
validity unit, then the sides, ranking, official eligibility, diagnostics and the rerun recommendation.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from . import canon, checks as checks_mod, gateway, review
from .rules import DEFAULT_RERUN_ON, LEGACY_ERROR_WHERE, RULESET, SETUP_EXCEPTIONS

NAME = "eo-judge"
VERSION = "0.1.0"
SCHEMA = "eo-verdict/1"
FAULT_CLASSES = ("agent", "plugin", "platform", "external", "undetermined")
TERMINATIONS = ("completed", "resigned", "no_show", "wall_cap", "platform_fault", "integrity_abort", "not_started")
CLASS_ORDER = {c: i for i, c in enumerate(FAULT_CLASSES)}
EFFECT_ORDER = {"void_match": 0, "void_side": 1, "recorded": 2}
# platform events (eo-run/1 platform/events.jsonl) that mean the platform did not deliver the match, when they
# happen before the match is over (later ones are the backend tearing it down)
FATAL_EVENTS = {"host_restart": "host_restart", "gateway_restart": "gateway_restart", "world_exit": "world_exit",
                "network_lost": "network_lost"}
CONTAINER_EVENTS = ("container_exit", "container_kill", "oom_kill")    # docker die / kill / oom, by compose service
WORLD_SERVICES = ("sim", "world")                                      # the official world's container
TEARDOWN_EVENTS = ("match_end", "seat_reclaimed", "cleanup")


@dataclass
class Facts:
    legacy: bool
    seats: list = field(default_factory=list)              # entrant seats
    side_of: dict = field(default_factory=dict)            # seat -> side
    sides: list = field(default_factory=list)              # every side, entrant first
    kind: dict = field(default_factory=dict)               # side -> entrant | platform
    entries: dict = field(default_factory=dict)            # side -> {seat: entry id}
    protocol: str | None = None
    result_kind: str = "winner"                            # winner | ranking | score
    end_reason: str | None = None                          # as the world recorded it
    end_where: str | None = None
    end_step: int | None = None
    end_ts: float | None = None
    start_ts: float | None = None                          # when play began (the first match_start / run row)
    prep_ts: float | None = None                           # when the preparation began (t0: the barrier opened)
    started: bool = False                                  # play began (a match_start / run row, or a later end)
    failed_before_start: bool = False                      # the platform could not start the match (B6)
    t0: dict = field(default_factory=dict)
    scores: dict = field(default_factory=dict)             # side -> number | None
    metrics: dict = field(default_factory=dict)            # side -> {}
    world_rank: dict = field(default_factory=dict)         # side -> rank the world gave (None: none)
    world_status: dict = field(default_factory=dict)       # side -> finished | retired | dnf | disqualified
    world_exit: dict = field(default_factory=dict)         # side -> None | resigned | no_show
    replay_ok: bool | None = None
    replay_note: str = ""
    replay_comparable: dict = field(default_factory=dict)  # {"comparable", "why", "run", "replay"} (R-REPLAY-FP)
    integrity: dict = field(default_factory=dict)
    entry_routes: dict = field(default_factory=dict)
    needed_items: set = field(default_factory=set)
    model_seats: list = field(default_factory=list)
    overrides: dict = field(default_factory=dict)
    seed: dict = field(default_factory=dict)
    continuous: str | None = None                          # the metrics key of the continuous score
    barrier_declared: bool = False                         # the task asked for the start barrier
    sources: dict = field(default_factory=dict)            # seat -> {source tag: acts}
    notes: dict = field(default_factory=dict)

    @property
    def match_s(self) -> float | None:
        """The match's actual duration: from the start of play to its end (wall seconds); None when either is
        unknown (the model access rule then uses its floor alone)."""
        if self.start_ts is None or self.end_ts is None or self.end_ts < self.start_ts:
            return None
        return round(self.end_ts - self.start_ts, 1)

    @property
    def session_s(self) -> float | None:
        """The session's actual duration, preparation and match (Chi 10-21, the model access rule): from t0 (the
        preparation's start) to the match end; the match alone when t0 is unknown (a legacy layout), None when the
        end is."""
        if self.prep_ts is None or self.end_ts is None or self.end_ts < self.prep_ts or (
                self.start_ts is not None and self.prep_ts > self.start_ts):
            return self.match_s
        return round(self.end_ts - self.prep_ts, 1)


# ---------------------------------------------------------------------------------------------- facts
def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _side_id(name: str) -> str:
    """A legacy platform side's name ("opponent", "scripted") as a SideId (common.schema.yaml: ^[A-Z][A-Z0-9]{0,7}$)."""
    t = "".join(ch for ch in str(name) if ch.isalnum()).upper()[:8]
    return t if t[:1].isalpha() else ("P" + t)[:8]


BUILD_KEYS = ("mujoco", "numpy", "blas", "blas_build", "blas_core", "threads")   # builds and thread settings
NATIVE_KEYS = ("cpu_simd", "numpy_simd")                                         # what a native run also needs


def replay_comparable(run_fp: dict | None, rep_fp: dict | None) -> dict:
    """R-REPLAY-FP: can a replay's result be compared with the match bit for bit? A replay made with the match (no
    fingerprint of its own: the fresh process in the match's container, same host and image) can. Another replay can
    when it ran the same image with the same builds and thread settings (framework/run/fingerprint.py: numeric mujoco,
    numpy, blas_build, blas_core, threads), and either both ran in portable float mode, or natively on the same CPU
    model and SIMD set (a native run replayed on another CPU diverges: handoff/rlopp_inventory_1020.md)."""
    if not rep_fp:
        return {"comparable": True, "why": "replayed with the match (same host and image)"}
    run_fp = run_fp or {}
    run_n = dict(run_fp.get("numeric") or {})
    rep_n = dict(rep_fp.get("numeric") or rep_fp)
    run_cpu = ((run_fp.get("host") or {}).get("cpu_model")) or run_fp.get("cpu_model")
    rep_cpu = ((rep_fp.get("host") or {}).get("cpu_model")) or rep_fp.get("cpu_model")
    keys = ("float_mode",) + BUILD_KEYS + NATIVE_KEYS
    base = {"run": {"cpu_model": run_cpu, **{k: run_n.get(k) for k in keys if k in run_n}},
            "replay": {"cpu_model": rep_cpu, **{k: rep_n.get(k) for k in keys if k in rep_n}}}
    img_run = ((run_fp.get("images") or {}).get("official_runtime"))
    img_rep = ((rep_fp.get("images") or {}).get("official_runtime"))
    if img_run and img_rep and img_run != img_rep:
        return {"comparable": False, "why": "the replay ran another official image", **base}
    if run_n.get("float_mode") is None:
        return {"comparable": False, "why": "the run's execution fingerprint does not record the float mode", **base}
    diff = [k for k in BUILD_KEYS if k in run_n and k in rep_n and run_n[k] != rep_n[k]]
    if diff:
        return {"comparable": False, "why": "builds or threads differ: " + ", ".join(diff), **base}
    if run_n.get("float_mode") == rep_n.get("float_mode") == "portable":
        return {"comparable": True, "why": "both in portable float mode, same builds", **base}
    if run_n.get("float_mode") != rep_n.get("float_mode"):
        return {"comparable": False, "why": "float modes differ", **base}
    if not run_cpu:
        return {"comparable": False, "why": "native float mode and the run's CPU model is not recorded", **base}
    diff = [k for k in NATIVE_KEYS if k in run_n and k in rep_n and run_n[k] != rep_n[k]]
    if run_cpu != rep_cpu or diff:
        return {"comparable": False, "why": "native float mode on another CPU (" +
                ", ".join((["cpu_model"] if run_cpu != rep_cpu else []) + diff) + ")", **base}
    return {"comparable": True, "why": "native float mode on the same CPU model, SIMD set and builds", **base}


def facts_of(ev) -> Facts:
    w = ev.world or {}
    v1 = ev.world_kind == "eo-world-report/1" or (not w and ev.task.get("kind") == "eo-taskspec/1")
    f = _facts_v1(ev, w) if v1 else _facts_legacy(ev, w)
    rep_fp = (ev.replay or {}).get("fingerprint") if isinstance(ev.replay, dict) else None
    f.replay_comparable = replay_comparable((ev.run or {}).get("execution_fingerprint"), rep_fp)
    if f.replay_ok is not None and not f.replay_comparable["comparable"]:
        f.replay_note = "replay not comparable: " + f.replay_comparable["why"] + \
            (f" (it {'agreed' if f.replay_ok else 'differed'})" if f.replay_ok is not None else "")
        f.replay_ok = None                                 # checks.replay n/a, never a replay fault
    f.failed_before_start = failed_before_start(ev, f)
    if f.failed_before_start:            # B6 (FWTEST2): no match was played, so nothing of a match is missing; the
        f.needed_items = set()           # platform's own records (abort.json, the backend's exit) say why
    for side in f.sides:                                   # who sat where (the Fixture, else the legacy run record)
        seats = [s for s in f.seats if f.side_of.get(s) == side]
        ent = {}
        for s in seats:
            e = (((ev.fixture or {}).get("seats") or {}).get(s) or {}).get("entry")
            if e:
                ent[s] = e
        if ent:
            f.entries[side] = ent
    return f


def failed_before_start(ev, f: Facts) -> bool:
    """B6 (FWTEST2 10-21): the platform could not start the match. No play began, and the platform's own records say
    it failed: the Runner aborted the Run (platform/abort.json: provisioning, the environment, the network pool), the
    backend exited non-zero, or the trial's setup raised. Such a Run is judged by that failure alone: the images it
    never started, the resources it never delivered and the match records it never wrote are not separate faults."""
    if f.started:
        return False
    p, run = ev.platform or {}, ev.run or {}
    if p.get("abort") is not None or run.get("state") == "aborted":
        return True
    if (p.get("end") or {}).get("code") not in (0, None):
        return True
    if any((e.get("ev") or e.get("kind")) == "backend_exit" and e.get("code") not in (0, None)
           for e in p.get("events") or [] if isinstance(e, dict)):
        return True
    tx = p.get("trial_exception") or {}
    return tx.get("type") in SETUP_EXCEPTIONS | {"AgentTimeoutError"}


def _facts_legacy(ev, d: dict) -> Facts:
    f = Facts(legacy=True)
    cfg = d.get("cfg") or {}
    f.seats = list(cfg.get("seats") or [])
    if not f.seats:                                        # no world report: the seats the backend knew
        run = ev.run or {}
        f.seats = list(ev.platform.get("seats") or []) or sorted((ev.platform.get("seat_exceptions") or {})) or \
            sorted(((ev.legacy.get("matchrun") or {}).get("agents") or {}).keys()) or \
            sorted(((ev.fixture or {}).get("seats") or {}).keys()) or sorted(run.get("sessions") or {}) or \
            sorted(((run.get("delivered") or {}).get("seats") or {}).keys())
    f.side_of = {s: (d.get("sides") or {}).get(s, s) for s in f.seats}
    for s in f.seats:
        if f.side_of[s] not in f.sides:
            f.sides.append(f.side_of[s])
    f.kind = {x: "entrant" for x in f.sides}
    scores = d.get("scores") or {}
    names: dict = {}                      # the legacy platform sides (a fixed opponent: "opponent", "scripted", ...)
    for x in [*scores, d.get("match_winner"), *(d.get("ranking") or [])]:
        if x is not None and x not in f.sides and x not in names:
            names[x] = _side_id(x)
            f.sides.append(names[x])
            f.kind[names[x]] = "platform"
    if names:
        f.notes["side_ids"] = dict(names)
    side = {v: k for k, v in names.items()}      # verdict side id -> legacy name
    proto = str(d.get("protocol") or ((ev.task.get("taskspec") or {}).get("protocol")) or "")
    f.protocol = "turn" if "turn" in proto else ("realtime" if proto else None)
    f.result_kind = "score" if d.get("solo") else ("ranking" if len(f.sides) > 2 else "winner")
    rows = ev.episode
    end = next((r for r in reversed(rows) if r.get("ev") == "end"), None)
    f.end_reason = d.get("reason") if d.get("phase", "over") == "over" or end is not None else None
    if end is not None:
        f.end_step, f.end_ts = end.get("k"), _num(end.get("ts"))
    elif f.end_reason is not None:
        f.end_step = d.get("steps")
    f.started = any(r.get("ev") in ("match_start", "run") for r in rows) or (
        not ev.episode_read and f.end_reason == "match_over")
    f.start_ts = _start_ts(rows)
    f.t0 = d.get("t0") or {}
    f.prep_ts = _prep_ts(rows) or _num(f.t0.get("epoch"))
    cont = ((d.get("continuous") or {}).get("by_side")) or {}
    if cont:
        f.continuous = "continuous"                        # the legacy name stays in diagnostics.legacy
        f.notes["continuous_name"] = (d.get("continuous") or {}).get("name")
    for x in f.sides:
        raw = scores.get(side.get(x, x))
        f.scores[x] = _num(raw)
        f.metrics[x] = dict(raw) if isinstance(raw, dict) else {}
        if _num(cont.get(side.get(x, x))) is not None:
            f.metrics[x]["continuous"] = cont[side.get(x, x)]
    winner = names.get(d.get("match_winner"), d.get("match_winner"))
    ranking = [names.get(x, x) for x in (d.get("ranking") or [])]
    if f.result_kind == "ranking" and ranking:
        f.world_rank = {x: (ranking.index(x) + 1 if x in ranking else None) for x in f.sides}
    elif f.result_kind == "winner" and winner in f.sides:
        f.world_rank = {x: (1 if x == winner else 2) for x in f.sides}
    elif f.result_kind == "winner" and d.get("decided_by") == "draw" and winner is None:
        f.world_rank = {x: 1 for x in f.sides}            # core 0.5.2: a draw the fixture allows (tied for first)
    else:
        f.world_rank = {x: None for x in f.sides}
    f.world_status = {x: "finished" for x in f.sides}
    f.world_exit = {x: None for x in f.sides}
    r = ev.replay                       # recomputed from the world report and the replay, never the world's own flag
    live = d.get("graded_by") == "live" and d.get("verdict_replay") is False   # Embodied First Exam: the live record
    if live:                                                                   # is the verdict (no grading replay)
        f.replay_ok, f.replay_note = None, "graded by the live match (no replay)"
    elif f.end_reason is not None and d.get("finalized"):
        if r is None:
            f.replay_ok, f.replay_note = False, "no replay_check.json"
        else:
            diffs = [k for k, a, b in (("state_sha", r.get("state_sha"), d.get("state_sha")),
                                       ("scores", r.get("scores"), d.get("scores")),
                                       ("winner", r.get("winner"), d.get("match_winner")),
                                       ("commands_sha", r.get("commands_sha"), d.get("commands_sha")),
                                       ("source_sha", r.get("source_sha"), d.get("source_sha")),
                                       ("steps", r.get("k"), d.get("steps"))) if a != b]
            if (d.get("continuous") or {}).get("by_side") is not None and \
                    r.get("continuous") != d["continuous"]["by_side"]:
                diffs.append("continuous")
            if d.get("seed_proof") and r.get("seed_commitment") != d["seed_proof"].get("commitment"):
                diffs.append("seed_commitment")
            f.replay_ok = not diffs
            f.replay_note = "differs: " + ", ".join(diffs) if diffs else ""
    lag = d.get("sim_lag") or {}
    if lag:
        f.integrity = {k: v for k, v in (("late_step_max_s", _num(lag.get("late_max_s"))),
                                         ("late_step_p99_s", _num(lag.get("late_p99_s"))),
                                         ("run_wall_s", _num(lag.get("run_wall_s"))),
                                         ("run_sim_s", _num(lag.get("run_sim_s"))),
                                         ("period_s", _num(lag.get("period_s")))) if v is not None}
    integ = d.get("integrity")
    if isinstance(integ, dict):          # core 0.4.0 writes the TaskSpec tolerance's readings into its ro-final/1
        f.integrity.update({k: v for k, v in integ.items()      # report (world lag, render and plan miss, ...): a
                            if isinstance(v, (int, float)) and not isinstance(v, bool)})   # gen-2 Task checks them all
    modes = d.get("player_modes") or {}
    f.model_seats = [s for s in f.seats if modes.get(s) == "model"]
    f.needed_items = ({"world_report", "episode"} | ({"replay_check"} if d.get("finalized") and not live else set()) |
                      {f"gateway.{s}" for s in f.model_seats}) if ev.world is not None else set()
    f.barrier_declared = ((d.get("taskspec") or {}).get("options") or {}).get("timing.t0") == "barrier"
    f.overrides = (d.get("taskspec") or {}).get("overrides") or {}
    proof = d.get("seed_proof") or {}
    f.seed = {"kind": "hidden" if proof.get("commitment") else "plain", "commitment": proof.get("commitment"),
              "value": None if proof.get("commitment") else d.get("seed")}
    for s, st in (d.get("control_sources") or {}).items() if isinstance(d.get("control_sources"), dict) else []:
        if isinstance(st, dict):
            f.sources[s] = {k: v for k, v in st.items() if isinstance(v, int)}
    return f


def _prep_ts(rows: list) -> float | None:
    """When the preparation began: the t0 row's epoch (core/phases.py: the barrier opened; the preparation deadline
    counts from it)."""
    r = next((x for x in rows if x.get("ev") == "t0"), None)
    return _num((r or {}).get("epoch"))


def _start_ts(rows: list) -> float | None:
    """When play began: the first match_start or run row's time (its started_epoch, else its ts)."""
    r = next((x for x in rows if x.get("ev") in ("match_start", "run")), None)
    if r is None:
        return None
    return _num(r.get("started_epoch")) or _num(r.get("ts"))


def _epoch(v):
    """An epoch from a number or a UTC ISO time (eo-world-report/1 writes arrivals as UTC text)."""
    if _num(v) is not None:
        return float(v)
    if isinstance(v, str):
        try:
            import datetime as _dt
            return _dt.datetime.strptime(v.rstrip("Z").split(".")[0], "%Y-%m-%dT%H:%M:%S").replace(
                tzinfo=_dt.timezone.utc).timestamp() + (float("0." + v.rstrip("Z").split(".")[1]) if "." in v else 0)
        except (ValueError, IndexError):
            return None
    return None


def _facts_v1(ev, w: dict) -> Facts:
    f = Facts(legacy=False)
    ts = ev.task.get("taskspec") or {}
    slots = ts.get("slots") or {}
    for side in slots.get("sides") or []:
        f.sides.append(side["id"])
        f.kind[side["id"]] = side.get("kind", "entrant")
        for seat in side.get("seats") or []:
            f.seats.append(seat["id"])
            f.side_of[seat["id"]] = side["id"]
    res = (w.get("result") or {}).get("sides") or {}
    for x in res:
        if x not in f.sides:
            f.sides.append(x)
            f.kind.setdefault(x, "entrant")
    for s in (w.get("seats") or {}):
        if s not in f.side_of:
            f.seats.append(s)
            f.side_of[s] = s
            if s not in f.sides:
                f.sides.append(s)
                f.kind[s] = "entrant"
    f.protocol = ts.get("protocol")
    f.result_kind = ((ts.get("scoring") or {}).get("result")) or ("ranking" if len(f.sides) > 2 else "winner")
    f.continuous = (((ts.get("scoring") or {}).get("continuous")) or {}).get("name")
    end = w.get("end") or {}
    reason = end.get("reason")
    f.end_reason = "completed" if reason == "match_over" else reason
    f.end_where, f.end_step = end.get("where"), end.get("step")
    erow = next((r for r in reversed(ev.episode) if r.get("ev") == "end"), None)
    f.end_ts = _num((erow or {}).get("ts")) or _epoch(((ev.run or {}).get("timeline") or {}).get("match_end"))
    f.start_ts = _start_ts(ev.episode) or _epoch(((ev.run or {}).get("timeline") or {}).get("match_start"))
    f.started = any(r.get("ev") in ("match_start", "run") for r in ev.episode) or bool(
        ((ev.run or {}).get("timeline") or {}).get("match_start")) or f.end_reason in ("completed", "resigned",
                                                                                         "wall_cap")
    t0 = w.get("t0") or {}
    f.t0 = {"source": t0.get("source"), "arrivals": {s: _epoch(a) for s, a in (t0.get("arrivals") or {}).items()}}
    f.prep_ts = _prep_ts(ev.episode) or _epoch(t0.get("epoch")) or \
        _epoch(((ev.run or {}).get("timeline") or {}).get("t0"))
    for x in f.sides:
        r = res.get(x) or {}
        f.scores[x] = _num(r.get("score"))
        f.metrics[x] = dict(r.get("metrics") or {})
        f.world_rank[x] = r.get("rank")
        st = r.get("status")
        f.world_status[x] = {"playing": "finished", None: "finished"}.get(st, st)
        f.world_exit[x] = None
    for e in w.get("exits") or []:
        if e.get("side") in f.world_exit:
            f.world_exit[e["side"]] = e.get("kind")
            f.world_status[e["side"]] = "retired"
    rp = w.get("replay") or {}
    if f.end_reason is not None and f.started:
        own = ev.replay
        eq = rp.get("fresh_process_equal")
        if own is not None and own.get("state_digest") and rp.get("state_digest"):
            same = (own.get("state_digest") == rp.get("state_digest") and
                    own.get("commands_digest") == rp.get("commands_digest") and own.get("steps") == rp.get("steps"))
            f.replay_ok = bool(same and eq is not False)
            f.replay_note = "" if f.replay_ok else "the sealed replay check differs from the world report"
        elif eq is not None:
            f.replay_ok, f.replay_note = bool(eq), "" if eq else "fresh_process_equal is false"
        else:
            f.replay_ok, f.replay_note = False, "no replay check"
    f.integrity = dict(w.get("integrity") or (((ev.run or {}).get("delivered") or {}).get("timing") or {}))
    entries = (ev.run or {}).get("entries") or {}
    for seat, e in entries.items():
        if isinstance(e, dict) and (e.get("route") or (e.get("model") or {}).get("route")):
            f.entry_routes[seat] = e.get("route") or e["model"]["route"]
    f.model_seats = sorted(set(ev.gateway) | {s for s in f.seats if f"gateway.{s}" in {m.get("name") for m in
                                                                                         ev.missing}})
    f.needed_items = {"world_report", "episode"} | ({"replay_check"} if f.started else set()) | \
        {f"gateway.{s}" for s in f.model_seats}
    f.barrier_declared = ((ts.get("timing") or {}).get("start_barrier")) is not None
    f.overrides = (ev.run or {}).get("overrides") or {}
    seed = (ev.fixture or {}).get("seed") or {}
    f.seed = {"kind": seed.get("kind"), "ref": seed.get("ref"), "value": seed.get("value")}
    for s, st in (w.get("seats") or {}).items():
        if isinstance(st, dict) and isinstance(st.get("sources"), dict):
            f.sources[s] = dict(st["sources"])
    return f


# ---------------------------------------------------------------------------------------------- faults
class Faults:
    def __init__(self, validity: dict):
        self.items: list = []
        self.validity = validity

    def add(self, cls, code, rule, scope="match", side=None, seat=None, at_step=None, evidence=(), note=""):
        f = {"class": cls, "code": code, "rule": rule, "scope": scope, "evidence": sorted(set(evidence)),
             "note": note}
        if side is not None:
            f["side"] = side
        if seat is not None:
            f["seat"] = seat
        if at_step is not None:
            f["at_step"] = at_step
        f["effect"] = self.effect(cls, scope)
        key = (cls, code, scope, side, seat)
        if not any((x["class"], x["code"], x["scope"], x.get("side"), x.get("seat")) == key for x in self.items):
            self.items.append(f)
        return f

    def effect(self, cls, scope) -> str:
        if (self.validity.get("faults") or {}).get(cls, "void") == "decide":
            return "recorded"
        if scope == "match" or self.validity.get("unit_effective") != "side":
            return "void_match"
        return "void_side"

    def voiding(self) -> list:
        return [x for x in self.items if x["effect"] != "recorded"]

    def sorted(self) -> list:
        return sorted(self.items, key=lambda f: (EFFECT_ORDER[f["effect"]], CLASS_ORDER[f["class"]], f["code"],
                                                 f.get("side") or "", f.get("seat") or ""))


def validity_of(ev) -> dict:
    """The Task's validity rules (eo-taskspec/1 `validity`); a legacy task gets the decided defaults."""
    ts = ev.task.get("taskspec") or {}
    v = ts.get("validity") if ev.task.get("kind") == "eo-taskspec/1" else None
    base = {"unit": "match", "separable_results": False, "separable_test_ref": None,
            "faults": {"agent": "decide", "plugin": "void", "platform": "void", "external": "void",
                       "undetermined": "void"}}
    out = {**base, **(v or {})}
    out["faults"] = {**base["faults"], **(out.get("faults") or {})}
    out["faults"]["agent"] = "decide"           # the agent's own problems are decided, never voided
    verified = out["unit"] == "side" and out.get("separable_results") and out.get("separable_test_ref")
    out["unit_effective"] = "side" if verified else "match"
    out["source"] = "taskspec" if v else "default"
    return out


def _seats_of_side(f: Facts, side) -> list:
    return [s for s in f.seats if f.side_of.get(s) == side]


def _arrived(f: Facts, seat) -> bool:
    return seat in (f.t0.get("arrivals") or {})


def _barrier(f: Facts) -> bool:
    """The start barrier was on: t0 opened at it, or the task asked for one and t0 never opened."""
    src = f.t0.get("source")
    return src in ("barrier", "barrier_timeout") or (src in (None, "none") and f.barrier_declared)


def end_faults(ev, f: Facts, F: Faults) -> str:
    """Faults from how the match ended; returns the termination."""
    if not f.legacy:
        return _end_v1(ev, f, F)
    rows = ev.episode
    kinds = {r.get("ev") for r in rows}
    reason = f.end_reason
    # the world's own timeout row, or the Runner's wall_cap event (it then stops the world: SIGUSR1 -> collected)
    wallcap = "match_timeout" in kinds or "wall_cap" in kinds or any(
        (e.get("ev") or e.get("kind")) == "wall_cap" for e in ((ev.platform or {}).get("events") or []))
    d = ev.world or {}
    if reason is None and wallcap and f.started:
        F.add("platform", "wall_cap", "R-WALLCAP", evidence=["platform_events"],
              note="the wall-clock cap ran out and the world never wrote its end; the match is void")
        return "wall_cap"
    if reason is None and breaches(ev) and f.started:
        return "integrity_abort"                 # the Runner ended the match, the world never wrote its end (hung)
    if reason is None:
        if ev.world is None or any(x["rule"] == "R-PLATFORM-EVENT" for x in F.items):
            return "platform_fault" if f.started else "not_started"      # the backend's own fault says why
        F.add("undetermined", "no_end", "R-TERM", evidence=["world_report"],
              note="the world report has no end: the match service stopped before the match ended")
        return "platform_fault" if f.started else "not_started"
    if reason == "wall_cap" or (wallcap and reason in ("abandoned", "collected")):
        F.add("platform", "wall_cap", "R-WALLCAP", at_step=f.end_step, evidence=["episode#match_timeout"],
              note="the wall-clock cap ran out; the match is void, not settled by the score")
        return "wall_cap"
    if reason == "match_over":
        return "completed"
    if reason == "resigned":                     # core 0.4.0: a side resigned and the match ended (eo-seat/1 9.7)
        ex = next((e for e in d.get("exits") or [] if e.get("kind") == "resigned"), {})
        seat = d.get("forfeiting") or ex.get("seat")
        side = ex.get("side") or f.side_of.get(seat, seat)
        F.add("agent", "resigned", "R-RESIGN", scope="side", side=side, seat=seat, at_step=ex.get("step", f.end_step),
              evidence=["world_report#exits"], note=f"side {side} resigned")
        if side in f.world_status:
            f.world_status[side], f.world_exit[side] = "retired", "resigned"
        return "resigned"
    if reason == "aborted":                      # core 0.4.0: the platform ended the match (SIGUSR2)
        if any(x.get("code") == "no_arrival" for x in d.get("faults") or []) and not f.started:
            for s in f.seats:                    # safeguard (b): no seat arrived by the barrier's wait + preparation:
                F.add("platform", "no_session", "R-NOSESSION", scope="seat", side=f.side_of.get(s), seat=s,
                      evidence=["world_report#faults"],     # the harness or its container never came up
                      note=f"seat {s} never opened its session; the Runner ended the Run (no seat arrived)")
            return "not_started"
        host_breach = [x for x in d.get("faults") or [] if x.get("code") == "integrity_abort"]
        if host_breach or breaches(ev):          # the Runner's abort at an integrity breach (integrity.abort)
            if not breaches(ev):                 # the Host's own record names where; the Runner's event, the metric
                for x in host_breach:
                    cls, code, seat = breach_fault(x.get("where"))
                    F.add(cls, code, "R-INTEGRITY", scope="seat" if seat else "match", side=f.side_of.get(seat),
                          seat=seat, at_step=x.get("at_step"), evidence=["world_report#faults"],
                          note=f"the Runner ended the match at an integrity breach ({x.get('where')})")
            return "integrity_abort"
        if not any(x.get("class") == "platform" for x in d.get("faults") or []):
            F.add("platform", "aborted", "R-PLATFORM-EVENT", at_step=f.end_step, evidence=["world_report#end"],
                  note="the platform ended the match (the Host's abort)")
        return "platform_fault"
    if reason == "clock":
        seat = d.get("forfeiting")
        side = f.side_of.get(seat, seat)
        F.add("agent", "clock", "R-CLOCK", scope="side", side=side, seat=seat, at_step=f.end_step,
              evidence=["episode#end"], note="the side's clock ran out")
        if side in f.world_status:
            f.world_status[side] = "dnf"
        return "completed"
    if reason == "ready_timeout":
        seat = d.get("forfeiting")
        F.add("platform", "review_timeout_end", "R-REVIEW", at_step=f.end_step, evidence=["episode#end"],
              note=f"the Host ended the match because seat {seat} missed a review (legacy rule); a missing review "
                   "never loses: the match should have resumed")
        return "platform_fault"
    if reason == "abandoned" and d.get("session_end_decides") is True:
        # Embodied First Exam: the agent's session ended while its match was in play (Harbor collects once the agent
        # is done): the side forfeits, the agent's own result (a valid loss), as a resignation
        seat = d.get("forfeiting")
        side = f.side_of.get(seat, seat)
        F.add("agent", "abandoned", "R-EXIT", scope="side", side=side, seat=seat, at_step=f.end_step,
              evidence=["world_report#exits"], note=f"seat {seat}'s session ended during the match (abandoned)")
        if side in f.world_status:
            f.world_status[side], f.world_exit[side] = "retired", "abandoned"
        return "resigned"
    if reason == "abandoned":
        F.add("platform", "session_end_ended_match", "R-EXIT", at_step=f.end_step, evidence=["episode#end"],
              note="the match was ended because the player session ended (legacy rule); a session end is only an "
                   "event")
        return "platform_fault"
    if reason in ("no_show", "incomplete", "collected"):
        # absent at the preparation deadline (start_timeout), or the sessions ended before it and the runner
        # collected the match early (collect_before_start: R-EXIT, the platform cut the window short)
        early = any(r.get("ev") == "collect_before_start" for r in rows)
        deadline = any(r.get("ev") == "start_timeout" for r in rows) or (reason == "no_show" and not early)
        if reason == "no_show" and d.get("session_end_decides") is True:
            deadline = True                      # Embodied First Exam: the session's end before the start is a no-show
        if reason == "incomplete" and f.started:
            F.add("platform", "review_timeout_end", "R-REVIEW", at_step=f.end_step, evidence=["episode#end"],
                  note="every seat due missed a review and the Host ended the match (legacy rule)")
            return "platform_fault"
        if reason == "collected" and f.started:
            F.add("platform", "collected_before_end", "R-EXIT", at_step=f.end_step, evidence=["episode#end"],
                  note="the match was stopped when the player sessions ended, before it was over (legacy rule)")
            return "platform_fault"
        return _absence(ev, f, F, deadline)
    if reason == "technical_error":
        return "platform_fault"                  # the errors themselves are the faults (error_faults)
    F.add("undetermined", "unknown_end_reason", "R-TERM", at_step=f.end_step, evidence=["world_report"],
          note=f"end reason {reason!r} is not one the judge knows")
    return "platform_fault"


def _absence(ev, f: Facts, F: Faults, deadline: bool) -> str:
    """No side played: the preparation closed (deadline) or the sessions ended first. A seat that never arrived at
    the barrier is the platform's (R-NOSESSION); one that arrived and never started is absent (R-NOSHOW) only at the
    deadline; before it, the platform stopped the match early (R-EXIT)."""
    d = ev.world or {}
    joined = d.get("joined") or {}
    absent = [s for s in f.seats if not joined.get(s)]
    for s in absent:
        side = f.side_of.get(s, s)
        if _barrier(f) and not _arrived(f, s) and d.get("session_end_decides") is not True:
            F.add("platform", "no_session", "R-NOSESSION", scope="seat", side=side, seat=s, evidence=["episode#t0"],
                  note=f"seat {s} never opened its session (the harness or its container never came up)")
        elif deadline:
            F.add("agent", "no_show", "R-NOSHOW", scope="side", side=side, seat=s, evidence=["episode#start_timeout"],
                  note=f"seat {s} had not sent start by the preparation deadline")
            f.world_status[side], f.world_exit[side] = "retired", "no_show"
    if not deadline and not any(x["code"] == "no_session" for x in F.items):
        F.add("platform", "collected_before_start", "R-EXIT", evidence=["episode#end"],
              note="the match was stopped when the player sessions ended, before the preparation deadline")
        return "not_started"
    return "no_show"


def _end_v1(ev, f: Facts, F: Faults) -> str:
    reason, where = f.end_reason, f.end_where or ""
    if reason is None and breaches(ev) and f.started:
        return "integrity_abort"                 # the Runner ended the match, the world never wrote its end (hung)
    if reason in (None, "not_started"):
        # arrivals are known only from a world report, and a match that started had every seat at the barrier
        missing = [s for s in f.seats if ev.world and not f.started and _barrier(f) and not _arrived(f, s)]
        for s in missing:
            F.add("platform", "no_session", "R-NOSESSION", scope="seat", side=f.side_of.get(s), seat=s,
                  evidence=["world_report#t0"], note=f"seat {s} never opened its session")
        if not missing and not any(x["rule"] == "R-PLATFORM-EVENT" for x in F.items):
            F.add("platform" if reason == "not_started" else "undetermined",
                  "not_started" if reason == "not_started" else "no_end", "R-TERM", evidence=["world_report"],
                  note="the match never started" if reason == "not_started" else
                  ("the world report has no end" if ev.world else "there is no world report"))
        return "platform_fault" if reason is None and f.started else "not_started"
    if reason == "completed":
        return "completed"
    if reason == "wall_cap":
        F.add("platform", "wall_cap", "R-WALLCAP", at_step=f.end_step, evidence=["world_report#end"],
              note="the wall-clock cap ran out; the match is void, not settled by the score")
        return "wall_cap"
    if reason in ("resigned", "no_show"):
        for e in (ev.world or {}).get("exits") or []:
            seat = e.get("seat")
            if e.get("kind") == "resigned":
                F.add("agent", "resigned", "R-RESIGN", scope="side", side=e.get("side"), seat=seat,
                      at_step=e.get("step"), evidence=["world_report#exits"], note="the side resigned")
            elif e.get("kind") == "no_show":
                seats = [seat] if seat else _seats_of_side(f, e.get("side"))
                never = [s for s in seats if _barrier(f) and not _arrived(f, s)
                         and (ev.world or {}).get("session_end_decides") is not True]   # Embodied First Exam
                for s in never:
                    F.add("platform", "no_session", "R-NOSESSION", scope="seat", side=e.get("side"), seat=s,
                          evidence=["world_report#t0"], note=f"seat {s} never opened its session")
                if not never:
                    F.add("agent", "no_show", "R-NOSHOW", scope="side", side=e.get("side"), seat=seat,
                          at_step=e.get("step"), evidence=["world_report#exits"],
                          note="no start by the preparation deadline")
        return reason
    if reason == "platform_fault":
        if where.startswith("plugin"):
            F.add("plugin", "plugin_fault", "R-PLUGIN", at_step=f.end_step, evidence=["world_report#end"],
                  note=f"the sport plugin failed ({where})")
        elif where.startswith("gateway."):
            seat = where.split(".", 1)[1]
            F.add("platform", "gateway_fault", "R-WORLD", scope="seat", side=f.side_of.get(seat), seat=seat,
                  at_step=f.end_step, evidence=["world_report#end"], note=f"the gateway of seat {seat} failed")
        elif where.startswith("provider."):
            seat = where.split(".", 1)[1]
            F.add("external", "provider_outage", "R-API-OUTAGE", scope="seat", side=f.side_of.get(seat), seat=seat,
                  at_step=f.end_step, evidence=["world_report#end"],
                  note=f"the Runner stopped the match: seat {seat}'s model service was out beyond the tolerance")
        elif where in ("world", "host", "render", "practice_gate", "metering", "integrity", "world_lag"):
            F.add("platform", f"{where}_fault", "R-WORLD", at_step=f.end_step, evidence=["world_report#end"],
                  note=f"the world service failed ({where})")
        else:
            F.add("undetermined", "world_fault", "R-WORLD", at_step=f.end_step, evidence=["world_report#end"],
                  note=f"the match ended on a fault the record does not place ({where or 'no location'})")
        return "platform_fault"
    if reason == "integrity_abort":              # the Runner ended the match at an integrity breach (at_breach)
        cls, code, seat = breach_fault(where)
        F.add(cls, code, "R-INTEGRITY", scope="seat" if seat else "match", side=f.side_of.get(seat), seat=seat,
              at_step=f.end_step, evidence=["world_report#end"],
              note=f"the Runner ended the match at an integrity breach ({where or 'no location'})")
        return "integrity_abort"
    F.add("undetermined", "unknown_end_reason", "R-TERM", at_step=f.end_step, evidence=["world_report#end"],
          note=f"end reason {reason!r} is not one the judge knows")
    return "platform_fault"


def retire_faults(ev, f: Facts, F: Faults) -> None:
    """Sides the Host retired while the others played on (more than two sides; legacy `retire` rows)."""
    for r in ev.episode:
        if r.get("ev") != "retire":
            continue
        side, seat, why = r.get("side", f.side_of.get(r.get("seat"))), r.get("seat"), r.get("why")
        if why == "ready_timeout":
            F.add("platform", "review_timeout_retire", "R-REVIEW", scope="side", side=side, seat=seat,
                  at_step=r.get("k"), evidence=["episode#retire"],
                  note=f"the Host retired side {side} because seat {seat} missed a review (legacy rule)")
        elif why == "abandoned":
            F.add("platform", "session_end_retire", "R-EXIT", scope="side", side=side, seat=seat,
                  at_step=r.get("k"), evidence=["episode#retire"],
                  note=f"the Host retired side {side} because its session ended (legacy rule)")
        elif why == "no_show":
            if _barrier(f) and not _arrived(f, seat):
                F.add("platform", "no_session", "R-NOSESSION", scope="seat", side=side, seat=seat,
                      at_step=r.get("k"), evidence=["episode#retire", "episode#t0"],
                      note=f"seat {seat} never opened its session")
            else:
                F.add("agent", "no_show", "R-NOSHOW", scope="side", side=side, seat=seat, at_step=r.get("k"),
                      evidence=["episode#retire"], note=f"seat {seat} had not sent start by the deadline")
                f.world_status[side], f.world_exit[side] = "retired", "no_show"
        elif why == "clock":
            F.add("agent", "clock", "R-CLOCK", scope="side", side=side, seat=seat, at_step=r.get("k"),
                  evidence=["episode#retire"], note="the side's clock ran out")
            f.world_status[side] = "dnf"
        elif why == "resigned":                  # core 0.4.0: a side resigned, the others play on
            F.add("agent", "resigned", "R-RESIGN", scope="side", side=side, seat=seat, at_step=r.get("k"),
                  evidence=["episode#retire"], note=f"side {side} resigned; the others played on")
            f.world_status[side], f.world_exit[side] = "retired", "resigned"
        else:
            f.world_status[side] = "dnf"         # a sport rule took the side out: the world's own decision


def error_faults(ev, f: Facts, F: Faults) -> None:
    legacy_errors = ((ev.world or {}).get("errors") or []) if f.legacy else []
    for e in legacy_errors:
        where = str(e.get("where") or "error")
        cls = e.get("class")
        if cls in FAULT_CLASSES:
            rule = "R-PLUGIN" if cls == "plugin" else "R-WORLD"
        else:
            cls, rule = LEGACY_ERROR_WHERE.get(where, ("undetermined", "R-WORLD"))
        F.add(cls, f"error_{where}", rule, evidence=["world_report#errors"],
              note=f"{where}: {str(e.get('error'))[:160]}")
    host = (ev.world or {}).get("faults") if f.legacy else None
    if isinstance(host, list):                   # core 0.4.0: the faults the Host observed (final.json `faults`)
        for x in host:
            if x.get("code") in ("integrity_abort", "no_arrival"):
                continue                         # the Runner's abort at a breach / no arrival: end_faults reads it
            cls = x.get("class") if x.get("class") in FAULT_CLASSES else "undetermined"
            code = str(x.get("code") or x.get("where") or "fault")[:60]
            rule = "R-WALLCAP" if code == "wall_cap" else {"plugin": "R-PLUGIN", "external": "R-API-OUTAGE",
                                                          "agent": "R-EXIT"}.get(cls, "R-WORLD")
            seat = x.get("seat")
            scope = "seat" if seat and cls != "plugin" else "match"   # the plugin is every seat's
            F.add(cls, code, rule, scope=scope, side=f.side_of.get(seat) if scope == "seat" else None,
                  seat=seat, at_step=x.get("at_step"), evidence=["world_report#faults"],
                  note=(f"{x.get('where')}: " if x.get("where") else "") + str(x.get("note") or "")[:200])
    for r in ([] if isinstance(host, list) else ev.episode):
        if r.get("ev") == "plugin_fault" or (r.get("ev") == "fault" and r.get("class") == "plugin"):
            F.add("plugin", f"plugin_{r.get('where') or 'fault'}", "R-PLUGIN", at_step=r.get("k"),
                  evidence=["episode#plugin_fault"], note=str(r.get("error") or "")[:160])
        elif r.get("ev") == "fault" and r.get("class") in FAULT_CLASSES:
            F.add(r["class"], str(r.get("code") or r.get("where") or "fault"),
                  "R-PLUGIN" if r["class"] == "plugin" else "R-WORLD", at_step=r.get("k"),
                  evidence=["episode#fault"], note=str(r.get("error") or r.get("note") or "")[:160])
    if f.legacy:
        for s, bad in sorted(((ev.world or {}).get("meter_error") or {}).items()):
            if bad:
                F.add("platform", "metering", "R-WORLD", scope="seat", side=f.side_of.get(s), seat=s,
                      evidence=["world_report#meter_error"], note=f"seat {s} was not metered")


def replay_faults(f: Facts, F: Faults) -> None:
    """A replay that does not reproduce the match: the plugin's when the platform's evidence is otherwise clean
    (fwspec 6.4), undetermined when the platform also failed."""
    if f.replay_ok is False:
        platform_trouble = any(x["class"] in ("platform", "undetermined") and x["effect"] != "recorded"
                               for x in F.items)
        F.add("undetermined" if platform_trouble else "plugin", "replay_mismatch", "R-REPLAY", at_step=f.end_step,
              evidence=["replay_check", "world_report"], note=f.replay_note)


def gateway_faults(ev, f: Facts, F: Faults) -> tuple[dict, str]:
    """The model access rule per model seat (gateway.MODEL_ACCESS_RULE, decided 10-21): a seat that lost more time to
    model-service failures than max(min_s, match_fraction x the session's actual duration, preparation + match: Chi
    10-21) voids the match, the fault's
    class by cause (the gateway: platform, the provider: external, else undetermined); error counts alone never void.
    Returns the per-seat reports and the rule."""
    ts = ev.task.get("taskspec") or {}
    tol = ((ts.get("integrity") or {}).get("tolerance") or {}) if ev.task.get("kind") == "eo-taskspec/1" else {}
    rule = gateway.MODEL_ACCESS_RULE
    limit = tol.get("model_access_lost") if isinstance(tol.get("model_access_lost"), dict) else \
        gateway.MODEL_ACCESS_DEFAULT
    threshold = gateway.access_threshold(limit, f.session_s)
    reports = {}
    for s in sorted(set(f.model_seats) | set(ev.gateway)):
        if s not in ev.gateway:
            if any(m.get("name") == f"gateway.{s}" for m in ev.missing) and not f.failed_before_start:
                F.add("undetermined", "gateway_log_missing", "R-GATEWAY-LOG", scope="seat", side=f.side_of.get(s),
                      seat=s, evidence=[f"gateway.{s}"], note=f"no gateway log for model seat {s}")
            continue
        rep = gateway.seat_report(ev.gateway[s], ev.usage.get(s), f.end_ts)
        rep["access"].update(threshold_s=threshold, session_s=f.session_s, match_s=f.match_s)
        reports[s] = rep
        acc = rep["access"]
        for cls in gateway.access_faults(acc, threshold):
            F.add(cls, "model_access_lost", "R-API-OUTAGE", scope="seat", side=f.side_of.get(s), seat=s,
                  evidence=[f"gateway.{s}"],
                  note=f"{rule}: seat {s} lost {acc['lost_s']} s of model access (gateway {acc['gateway_s']} s, "
                       f"provider {acc['provider_s']} s, undetermined {acc['unknown_s']} s; calls before the match "
                       f"end, the preparation's included) > {threshold} s = max({limit.get('min_s')} s, "
                       f"{limit.get('match_fraction')} x "
                       + (f"the {f.session_s} s session: preparation + match)" if f.session_s is not None
                          else "a match that never ran)"))
        if rep["unlogged_failures"] and f.end_reason is not None:
            F.add("undetermined", "gateway_log_incomplete", "R-GATEWAY-LOG", scope="seat",
                  side=f.side_of.get(s), seat=s, evidence=[f"gateway.{s}", f"gateway_usage.{s}"],
                  note=f"the gateway counted {rep['unlogged_failures']} failure(s) it never logged")
    return reports, rule


def _seat_of_service(service: str, seats) -> str | None:
    """The seat a compose service belongs to (seat_a / seat-a / seata for seat A); None for any other service."""
    s = service.lower().replace("-", "_")
    return next((x for x in seats if s in (f"seat_{x.lower()}", f"seat{x.lower()}")), None)


def _match_over_t(f: Facts, rows: list) -> float | None:
    """When the match was over, for the platform's events: the world's own end (its end row; the Run's timeline),
    else the backend's first match_end / seat_reclaimed / cleanup event; None when nothing says (every event counts).
    Container events after it are the backend tearing the match down."""
    if f.end_ts is not None:
        return f.end_ts
    ts = [_num(e.get("t")) or _epoch(e.get("at")) for e in rows if (e.get("ev") or e.get("kind")) in TEARDOWN_EVENTS]
    ts = [t for t in ts if t is not None]
    return min(ts) if ts else None


BREACH_WHERE = {"world": ("platform", "world_lag_max"), "world_lag": ("platform", "world_lag_max"),
                "world_lag_max": ("platform", "world_lag_max"), "world_stall": ("platform", "world_stall"),
                "heartbeat": ("platform", "world_stall")}
BREACH_SEAT = {"gateway": "platform", "provider": "external", "model": "undetermined"}   # model access, by cause


def breach_fault(where: str | None) -> tuple[str, str, str | None]:
    """(class, code, seat) of an integrity breach the Runner ended the match for (integrity.abort = at_breach), from
    where it happened: the world's single lag spike (world: world_lag_max), the heartbeat (world_stall), a seat's model
    access by cause (gateway.<seat>: platform, provider.<seat>: external, model.<seat>: undetermined)."""
    w = str(where or "")
    if w in BREACH_WHERE:
        return (*BREACH_WHERE[w], None)
    head, _, seat = w.partition(".")
    if head in BREACH_SEAT and seat:
        return BREACH_SEAT[head], "model_access_lost", seat
    return "platform", "integrity_abort", None


def breaches(ev) -> list:
    """The Runner's integrity_breach events (platform/events.jsonl), in order."""
    return [e for e in (ev.platform or {}).get("events") or []
            if isinstance(e, dict) and (e.get("ev") or e.get("kind")) == "integrity_breach"]


def platform_faults(ev, f: Facts, F: Faults) -> dict:
    """Backend events before the match was over: what kept the match from being delivered is the platform's (the
    world's container dying, a seat's container stopped by the platform, an injected fault, a backend that failed
    before the match ended); a harness exit, a seat container ending on its own and another service's container
    (Harbor's main, a practice sidecar) are events."""
    p = ev.platform or {}
    tx = p.get("trial_exception")
    events: dict = {}
    if tx and tx.get("type"):
        events["trial"] = tx["type"]
        if not f.started and tx["type"] in SETUP_EXCEPTIONS | {"AgentTimeoutError"} and f.end_reason in (
                None, "collected", "incomplete", "no_show", "not_started"):
            F.add("platform", f"backend_{tx['type']}", "R-PLATFORM-EVENT", evidence=["platform_events"],
                  note=f"{tx['type']}: {tx.get('message', '')[:160]}")
    for s, x in sorted((p.get("seat_exceptions") or {}).items()):
        events[s] = x.get("type")
        if not x.get("setup_done") and x.get("type") in SETUP_EXCEPTIONS and not f.started:
            F.add("platform", f"seat_setup_{x['type']}", "R-PLATFORM-EVENT", scope="seat", side=f.side_of.get(s),
                  seat=s, evidence=["platform_events"], note=f"seat {s}: {x.get('message', '')[:160]}")
    rows = p.get("events") or []                          # eo-run/1: platform/events.jsonl ({at, t, ev, ...})
    over = _match_over_t(f, rows)
    ended_by_runner = [_num(e.get("t")) for e in rows if (e.get("ev") or e.get("kind")) in
                       ("integrity_breach", "no_arrival") and _num(e.get("t")) is not None]
    cut = min(ended_by_runner) if ended_by_runner else None   # from then on the platform ends its own match (the
    #                                                              abort, a world it stopped): no fault of its own
    for e in rows:
        kind, seat = e.get("kind") or e.get("ev") or e.get("event"), e.get("seat")
        if kind == "harness_exit":
            continue
        t = _num(e.get("t")) or _epoch(e.get("at"))
        if e.get("during_match") is False or (e.get("during_match") is None and over is not None and t is not None
                                              and t > over):
            continue                                       # after the match: the backend tearing it down
        if cut is not None and t is not None and t > cut and kind in CONTAINER_EVENTS + ("world_stopped",):
            continue
        code, cls, rule = FATAL_EVENTS.get(kind), "platform", "R-PLATFORM-EVENT"
        service = str(e.get("service") or "")
        if kind in CONTAINER_EVENTS:
            seat = seat or _seat_of_service(service, f.seats)
            if service in WORLD_SERVICES or service.startswith("world"):
                code, seat = ("world_oom_kill" if kind == "oom_kill" else "world_exit"), None   # the official world
            elif seat and (kind == "container_kill" or e.get("by") in ("host", "backend")):
                code = "seat_killed"                       # the platform stopped a seat's container mid-match
            elif seat and kind == "oom_kill":
                code, cls, rule = "seat_oom", "agent", "R-EXIT"   # its own programs outgrew the declared memory
            else:
                code = None    # a seat's container ending on its own, or another service (Harbor's main, a practice
                #                sidecar): an event; what it did to the match shows in the world's end (R-EXIT)
            if code is None and service:
                events.setdefault("containers", []).append(f"{kind}:{service}")
        elif kind == "fault_injected":
            code = "fault_injected"                        # the Runner's own fault injection (the rerun path's test)
        elif kind == "integrity_breach":                   # the Runner ended the match at a breach (at_breach)
            cls, code, seat = breach_fault(e.get("where"))
            rule = "R-INTEGRITY"
            e = {**e, "note": f"the Runner ended the match: {e.get('metric')} {e.get('value')} > {e.get('limit')} "
                              f"at {e.get('where')}"}
        if code:
            F.add(cls, code, rule, scope="seat" if seat else "match",
                  side=f.side_of.get(seat) if seat else None, seat=seat, evidence=["platform_events"],
                  note=f"{kind}{' of seat ' + seat if seat else ''}{' (' + service + ')' if service else ''}"
                       f"{' code ' + str(e.get('code')) if e.get('code') is not None else ''}"
                       f"{' signal ' + str(e.get('signal')) if e.get('signal') is not None else ''}"
                       f"{': ' + str(e.get('note'))[:120] if e.get('note') else ''}")
    end = p.get("end") or {}                               # the backend's own end record (platform/end.json)
    bexit = [e for e in rows if (e.get("ev") or e.get("kind")) == "backend_exit" and e.get("code") not in (0, None)]
    if (f.end_reason is None or not f.started) and (bexit or end.get("code") not in (0, None)):
        code = bexit[0].get("code") if bexit else end.get("code")
        F.add("platform", "backend_failed", "R-PLATFORM-EVENT", evidence=["platform_events"],
              note=f"the backend exited with code {code} ({end.get('ended') or 'backend_exit'}) and the match "
                   f"{'never started' if not f.started else 'has no end'}")
    ab = p.get("abort")
    if ab is not None:                                     # the Runner aborted the Run (provisioning or the match)
        why = str(ab.get("reason") or "aborted")
        cls = "external" if why.startswith("provider") else "platform"
        F.add(cls, f"aborted_{why}"[:60], "R-PLATFORM-EVENT", evidence=["platform/abort.json"],
              note=f"the Runner aborted the Run ({why}): {str(ab.get('detail') or '')[:160]}")
    if (ev.run or {}).get("state") == "aborted" and ab is None:
        F.add("platform", "aborted", "R-PLATFORM-EVENT", evidence=["run_record"],
              note="the Run was aborted (provisioning or the match failed)")
    return events


def input_faults(res, F: Faults) -> None:
    rule_cls = {"fixture_matches": "platform", "release_matches": "platform", "images_match_lock": "platform",
                "delivered_resources": "platform", "integrity": "platform", "routes_match_entries": "platform",
                "carry_matches": "platform", "evidence_complete": "undetermined"}
    for name, cls in rule_cls.items():
        for code, note in res.why.get(name, []):
            F.add(cls, code, "R-INTEGRITY" if name == "integrity" else "R-INPUT", evidence=[name], note=note[:300])


def _outage_excuses(F: Faults) -> None:
    """D2 rule (ii): a seat that missed a deadline (no start, its clock) while its own model service was failing did
    not miss it of its own doing: the agent fault goes, the outage fault says what it caused."""
    out = {x.get("seat"): x for x in F.items if x["rule"] == "R-API-OUTAGE" and x["effect"] != "recorded"}
    keep = []
    for x in F.items:
        if x["class"] == "agent" and x["code"] in ("no_show", "clock") and x.get("seat") in out:
            o = out[x["seat"]]
            o["note"] += f"; seat {x['seat']} also missed a deadline during it ({x['code']}): not counted as its own"
            continue
        keep.append(x)
    F.items[:] = keep


# ---------------------------------------------------------------------------------------------- the verdict
def _ids(ev, f: Facts) -> tuple[str, str]:
    run, fx = ev.run or {}, ev.fixture or {}
    if run.get("run_id"):
        return (fx.get("fixture_id") or (run.get("fixture") or {}).get("id") or run["run_id"].split("/run-")[0],
                run["run_id"])
    d = ev.world or {}
    basis = {"taskspec": (d.get("taskspec") or {}).get("sha256"), "seed": f.seed, "first": d.get("first"),
             "t0": (d.get("t0") or {}).get("epoch"), "seats": f.seats}
    if not d:                                     # never started: the backend's own trial name is all there is
        basis = {"trial": ev.root.name, "seats": f.seats}
    fid = "LEGACY-" + canon.digest(basis)[7:19]
    return fid, fid + "/run-1"


def _task_release(ev, f: Facts, res) -> str:
    """The release the Run executed: the Fixture's (what the Run was bound to; a recomputed digest that differs is a
    failed check and goes to diagnostics.release_recomputed), else the Run's, else the recomputed one."""
    for v in ((((ev.fixture or {}).get("task")) or {}).get("release"), (ev.run or {}).get("task_release"),
              res.notes.get("release")):
        if v:
            return v
    if res.notes.get("taskspec_sha256"):
        f.notes["task_release_from"] = "the sealed TaskSpec file's sha256 (a legacy task has no release digest)"
        return "sha256:" + res.notes["taskspec_sha256"]
    said = ((ev.world or {}).get("taskspec") or {}).get("sha256")
    if said:
        f.notes["task_release_from"] = "the match service's report of its TaskSpec file (no sealed Task files)"
        return "sha256:" + said
    f.notes["task_release_from"] = "unknown (no world report, no Task files)"
    return canon.digest({"task": "unknown", "root": ev.root.name})


CODE_FILES = ("__init__.py", "canon.py", "checks.py", "evidence.py", "gateway.py", "legacy.py", "project.py",
              "review.py", "rules.py", "verdict.py", "verifier.py")


def code_digest() -> str:
    """Digest of the judging code: the modules that decide a verdict (the same in the repository and in a task's
    tests/eo_judge/; the command line, the old-and-new comparison and the legacy helper seeds.py are not judging)."""
    here = Path(__file__).resolve().parent
    files = {n: canon.file_digest(here / n) for n in CODE_FILES if (here / n).is_file()}
    return canon.tree_digest(files)


def _blockers(ev, f: Facts, valid: bool, legacy_official: dict | None) -> list:
    out = []
    fx = ev.fixture
    if fx is None or fx.get("kind") != "official":
        out.append("adhoc_fixture")
    hidden = f.seed.get("kind") == "hidden" and (not f.legacy or (legacy_official or {}).get("hidden_seed_index")
                                                 is not None)
    if not hidden:
        out.append("dev_seed")
    if (ev.task.get("release") or {}).get("status") != "frozen":
        out.append("candidate_release")
    if not ((ev.run or {}).get("backend") or {}).get("certification"):
        out.append("uncertified_backend")
    pre = ev.preflight or {}
    if any(c.get("waived") for c in pre.get("checks") or [] if isinstance(c, dict)):
        out.append("waived_requirements")
    if f.overrides:
        out.append("runtime_override")
    if not valid:
        out.append("invalid")
    return out


def _platform_services(F: Faults, reports: dict, events: dict, f: Facts) -> str:
    """The platform's own services (the world's container, the gateway, render pool, snapshot store, the backend):
    fail when such a platform fault is on record, pass when there are platform events or gateway logs and nothing
    failed, n/a when there is nothing to tell."""
    bad = {"metering", "gateway_fault", "gateway_outage", "render_fault", "gateway_restart", "snapshot_store",
           "model_access_lost", "world_stall",
           "world_exit", "world_oom_kill", "fault_injected", "host_restart", "network_lost", "backend_failed"}
    if any(x["class"] == "platform" and x["code"] in bad for x in F.items):
        return "fail"
    if reports or events:
        return "pass"
    return "n/a"


def judge(ev, *, sport_fields: dict | None = None, audits: dict | None = None, legacy_official: dict | None = None,
          now: float | None = None) -> dict:
    """The verdict of one Run (eo-verdict/1). `sport_fields`: the sport's own numbers (the legacy scoring hook's
    evaluate(final)); `audits`: legacy direct play's no-code audit {seat: (tool calls, violations)};
    `legacy_official`: the legacy official-configuration reading {"official_config", "hidden_seed_index"}."""
    t_start = time.time() if now is None else now
    f = facts_of(ev)
    validity = validity_of(ev)
    F = Faults(validity)
    res = checks_mod.run_checks(ev, f)
    events = platform_faults(ev, f, F)
    termination = end_faults(ev, f, F)
    retire_faults(ev, f, F)
    error_faults(ev, f, F)
    reports, api_rule = gateway_faults(ev, f, F)
    input_faults(res, F)
    replay_faults(f, F)
    if audits:
        for s, (_calls, bad) in sorted(audits.items()):
            if bad and (ev.world or {}).get("play") == "direct":
                side = f.side_of.get(s, s)
                F.add("agent", "nocode_violation", "R-NOCODE", scope="side", side=side, seat=s,
                      evidence=["gateway." + s], note=f"{len(bad)} tool call(s) in direct play")
                f.world_status[side] = "disqualified"
    _outage_excuses(F)
    if termination in ("platform_fault", "integrity_abort", "not_started") and not F.voiding():
        # a match that never ran to an end cannot be a result, even when no record says why (R-COMPLETE)
        F.add("undetermined", "no_cause_recorded", "R-COMPLETE", evidence=["world_report"],
              note=f"the match ended as {termination} and no record names a cause")
    ordered = F.sorted()
    fault_rules = [x["rule"] for x in ordered]
    faults = [{k: v for k, v in x.items() if k != "rule"} for x in ordered]    # eo-verdict/1 has no `rule` field
    for x, rule in zip(faults, fault_rules):
        x["note"] = f"{rule}: {x['note']}" if x["note"] else rule
    valid = not any(x["effect"] == "void_match" for x in faults)
    void_sides = {x.get("side") for x in faults if x["effect"] == "void_side"}
    sides, ranking, winner = _sides(f, valid, void_sides)
    checks = dict(res.value)
    checks["platform_services"] = _platform_services(F, reports, events, f)
    blockers = _blockers(ev, f, valid, legacy_official)
    fx = ev.fixture
    rerun_on = set(((fx or {}).get("rerun") or {}).get("on_faults") or DEFAULT_RERUN_ON)
    rerun_faults = [x for x in faults if x["effect"] != "recorded" and x["class"] in rerun_on]
    rerun = {"recommended": bool(rerun_faults),
             "reason": f"{rerun_faults[0]['class']}/{rerun_faults[0]['code']}" if rerun_faults else None}
    fid, rid = _ids(ev, f)
    tr = _task_release(ev, f, res)
    rules_digest = ((((ev.task.get("lock") or {}).get("artifacts") or {}).get("judge")) or {}).get("digest") or \
        canon.digest({"ruleset": RULESET})
    diagnostics = _diagnostics(ev, f, validity, reports, api_rule, events, legacy_official, sport_fields)
    diagnostics["fault_rules"] = fault_rules                 # the rule behind each fault, in the faults' order
    if res.notes.get("release") and res.notes["release"] != tr:
        diagnostics["release_recomputed"] = res.notes["release"]
    if res.notes.get("integrity_unmeasured"):               # declared tolerances the world gave no reading for
        diagnostics["integrity_unmeasured"] = res.notes["integrity_unmeasured"]
    verdict = {
        "schema": SCHEMA, "fixture_id": fid, "run_id": rid, "task_release": tr, "valid": valid,
        "official": {"eligible": not blockers, "blockers": blockers},
        "termination": termination, "sides": sides, "winner": winner, "ranking": ranking, "faults": faults,
        "checks": checks, "diagnostics": diagnostics, "rerun": rerun,
        "evidence_digest": ev.evidence_digest,
        "judge": {"name": NAME, "version": VERSION, "rules": rules_digest,
                  "digest": canon.digest({"code": code_digest(), "rules": rules_digest}), "offline": True},
        "meta": {"judged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t_start)), "layout": ev.layout,
                 "wall_s": 0.0 if now is not None else round(time.time() - t_start, 3)},
    }
    return verdict


def _diagnostics(ev, f: Facts, validity, reports, api_rule, events, legacy_official, sport_fields) -> dict:
    if ev.episode_read:
        rv = review.diagnose(ev.episode, f.seats, f.protocol, f.side_of)
    else:
        rv = {"rule": review.RULE, "by_seat": {}, "missing": []}
    reviews = {s: {k: x[k] for k in ("due", "submitted", "missing", "empty", "template", "undetermined")}
               for s, x in rv["by_seat"].items()}
    harness = {}
    for s, x in sorted(((ev.platform or {}).get("seat_exceptions") or {}).items()):
        harness[s] = [{"type": x.get("type"), "setup_done": bool(x.get("setup_done"))}]
    for e in (ev.platform or {}).get("events") or []:
        if (e.get("kind") or e.get("event")) == "harness_exit" and e.get("seat"):
            harness.setdefault(e["seat"], []).append({k: e.get(k) for k in ("at", "code", "step") if k in e})
    out = {
        "ruleset": RULESET,
        "reviews": reviews,
        "review_detail": {"rule": rv["rule"], "missing": rv["missing"],
                          "template_seat": {s: x["template_seat"] for s, x in rv["by_seat"].items()},
                          "sources": {s: x["sources"] for s, x in rv["by_seat"].items()}},
        "refused": _refused(ev, f),
        "harness_exits": harness,
        "sources": f.sources,
        "validity": {k: validity[k] for k in ("unit", "unit_effective", "separable_results", "separable_test_ref",
                                              "source")},
        "external_rule": api_rule,
        "model_api": {s: {k: r[k] for k in ("calls", "completed", "errors_by_cause", "after_match_end",
                                            "unlogged_failures", "rule", "errors", "routes", "deployments")}
                      for s, r in sorted(reports.items())},
        "model_access": {s: dict(r["access"]) for s, r in sorted(reports.items())},
        "platform_events": events,
        "integrity": f.integrity,
        "replay": {"comparable": f.replay_comparable.get("comparable"), "why": f.replay_comparable.get("why"),
                   **({"note": f.replay_note} if f.replay_note else {}),
                   **({k: f.replay_comparable[k] for k in ("run", "replay")} if "run" in f.replay_comparable
                      else {})},
        "world_end": {"reason": f.end_reason, "where": f.end_where, "step": f.end_step,
                      "scores": {x: f.scores.get(x) for x in f.sides}},
        "scoring": {"result": f.result_kind, "continuous": f.continuous},
    }
    if f.legacy:
        out["legacy"] = {k: v for k, v in {
            "side_ids": f.notes.get("side_ids"), "continuous_name": f.notes.get("continuous_name"),
            "task_release_from": f.notes.get("task_release_from"),
            "taskspec": {k: ((ev.world or {}).get("taskspec") or {}).get(k) for k in ("id", "sha256", "overrides")},
            "official_config": (legacy_official or {}).get("official_config"),
            "hidden_seed_index": (legacy_official or {}).get("hidden_seed_index")}.items() if v is not None}
    if sport_fields is not None:
        out["sport_fields"] = {k: sport_fields[k] for k in sorted(sport_fields)}
    pol = task_policies(ev)
    if pol is not None:                     # an Engineer Task's preset platform policies ([] = none given; Chi 10-31)
        out["policies"] = pol
    return out


def task_policies(ev) -> list | None:
    """The Engineer seat's preset platform policies the Task gave (TaskSpec v1 tools.policies, else the runtime
    TaskSpec's policies); None for a Task that records none (an Athlete Task, a Task generated before 10-31)."""
    ts = (getattr(ev, "task", None) or {}).get("taskspec") or {}
    v = (ts.get("tools") or {}).get("policies") if isinstance(ts.get("tools"), dict) else None
    if v is None:
        v = ts.get("policies")
    return [str(x) for x in v] if isinstance(v, list) else None


def _sides(f: Facts, valid: bool, void_sides: set) -> tuple[dict, list, str | None]:
    out = {}
    live = [x for x in f.sides if valid and x not in void_sides]
    ranks = {}
    if f.result_kind != "score":
        order = sorted((f.world_rank.get(x) if f.world_rank.get(x) is not None else 10 ** 6, i, x)
                       for i, x in enumerate(f.sides) if x in live)
        rank, prev = 0, None
        for n, (r, _i, x) in enumerate(order, 1):
            if r >= 10 ** 6:
                ranks[x] = None
                continue
            if r != prev:
                rank, prev = n, r
            ranks[x] = rank
    for x in f.sides:
        side_valid = valid and x not in void_sides
        rec = {"kind": f.kind.get(x, "entrant"),
               "status": f.world_status.get(x, "finished") if side_valid else "void",
               "exit": f.world_exit.get(x) if side_valid else None,
               "score": f.scores.get(x) if side_valid else None,
               "rank": ranks.get(x) if side_valid else None,
               "metrics": f.metrics.get(x, {}) if side_valid else {}, "valid": side_valid}
        if f.entries.get(x):
            rec["entries"] = f.entries[x]
        out[x] = rec
    ranking = sorted((x for x in live if ranks.get(x) is not None), key=lambda x: (ranks[x], f.sides.index(x)))
    winner = None
    if valid and f.result_kind != "score" and ranking:
        firsts = [x for x in ranking if ranks[x] == 1]
        winner = firsts[0] if len(firsts) == 1 else None
    return out, ranking, winner


def _refused(ev, f: Facts) -> dict:
    out = {}
    stats = (ev.world or {}).get("seats") or {}
    for s in f.seats:
        st = stats.get(s) or {}
        if not isinstance(st, dict):
            continue
        r = st.get("refused") if isinstance(st.get("refused"), dict) else {}
        keys = ("refused_invalid", "refused_busy", "refused_not_model", "refused_ready_program", "refused_turn",
                "http_429_rate", "http_429_open", "http_429_conn", "observe_busy")
        vals = {k: st[k] for k in keys if isinstance(st.get(k), (int, float)) and st.get(k)}
        vals.update({k: v for k, v in r.items() if isinstance(v, (int, float)) and v})
        if vals:
            out[s] = dict(sorted(vals.items()))
    return out


def verdict_bytes(verdict: dict) -> bytes:
    """The normalized verdict: JCS of everything but `meta` (what re-judging must reproduce byte for byte)."""
    return canon.jcs({k: v for k, v in verdict.items() if k != "meta"})


def verdict_digest(verdict: dict) -> str:
    return canon.PREFIX + canon.sha256_hex(verdict_bytes(verdict))
