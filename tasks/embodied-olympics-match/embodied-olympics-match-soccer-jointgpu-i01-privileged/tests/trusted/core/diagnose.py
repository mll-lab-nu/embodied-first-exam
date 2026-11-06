"""Post-match diagnosis (core 0.2.25; capability measurement framework §7): read a finished match's records, replay
its world deterministically, and run the sport's analysis (sports/<sport>/diagnose.py). Nothing here is part of a
match: no match imports it, it changes no record, and a bug in it changes no official result.

    python -m core.diagnose PLUGIN RUN_DIR [--diagnose FILE] [--out DIR] [--no-sport]

RUN_DIR holds episode.jsonl (or episode.jsonl.gz) and, when there are any, final.json, replay_check.json,
local_result.json and the program snapshots (snapshots/, or ../snapshots/ and ../../snapshots/ of a Harbor trial:
tools/snapshot_watch.py). Writes RUN_DIR/diag/ (or --out): units.jsonl, claims.jsonl, summary.json.

The sport's analysis, sports/<sport>/diagnose.py (never copied into a task: tools/sportlib.NOT_IN_SIM):
    units(rep) -> [{"id", "seat", "k0", "k1", ...}]               decision units (one incoming ball, one possession ...)
    implied(rep, units) -> [{"unit", "seat", "k_cmd", "act_id", "quantity", "implied", "truth", "err_space",
                             "err_time", ...}]                     claims read from the commands, with the true value
    metrics(units, claims) -> {seat: {metric_id: {"value", "capability", "status", ...}}}
        capability in A1 A2 A3 A4 B1 B2 B3 C1 C2; status in official conditional behaviour unvalidated
Looked up as --diagnose, else diagnose.py next to PLUGIN, else sports/<sport>/diagnose.py of this repository.

rep = load(run_dir, plugin) (INTERFACE "diag/1"):
    interface, run_dir, plugin, sport, protocol, revision, core_version, header, cfg (dict), seats, sides
        {seat: side}, dt (control step, s; None without a plugin)
    rows                      every row of episode.jsonl, in order
    cmd, observe, act_received, effect, act_dropped, event, team, team_delivered, unit_over, resume, ready, review,
    forfeit, retire, end      the rows of that "ev", in order ([] when the episode has none)
    has                       {name: bool}: which diagnostic rows the episode has (core >= 0.2.25 writes them)
    obs                       {seat: {obs_id: observe row}}
    acts                      {seat: [act]} in act_id order; act = {act_id, seat, entity, k_recv, unit, decision,
                              obs_id_last, obs (its observe row or None), k_obs, view_steps, seen, k_effect (None:
                              no effect), cmd (the low-level command that took effect, or None), rejected, dropped
                              (why, or None)}
    events                    [{"k", **event}]: every event Match.step() returned (event rows, flattened)
    final, replay_check, local_result     those JSON files, or None
    snapshots                 {"dir", "rows": snapshots.jsonl rows, "procs": procs.jsonl rows} per seat, or {}
    world                     world(build=None) -> World: a fresh deterministic replay (below); build(cfg) -> Match
                              replaces the sport's build (e.g. a screening variant's patched opponent)
World (realtime: k = control steps; turn: k = Match.k, the actions so far):
    w.at(k, after=False)      the Match with m.k == k, as the seats saw it at k: before the rows logged at k
                              (commands that took effect before step k); after=True: after them. Forward is cheap,
                              backward rebuilds from the start.
    w.m, w.k                  the match now and its step
    w.events                  {k: events} that Match.step() returned while replaying (also for old episodes)
    w.run(fn)                 calls fn(m) at every step to the end (realtime: after each step; turn: after each row)
    w.fork()                  an independent match in the same state (counterfactual play): a deep copy, else a
                              second replay to the same point
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import importlib.util
import json
import math
import os
import statistics
import sys
from pathlib import Path

from .episode import REPLAYED, _dispatch, header_cfg, load_plugin
from .sport import FINISHED

INTERFACE = "diag/1"
ROWS = ("cmd", "observe", "act_received", "effect", "act_dropped", "event", "team", "team_delivered", "unit_over",
        "resume", "ready", "review", "forfeit", "retire", "end")
DIAG = ("observe", "act_received", "effect", "act_dropped", "event", "team_delivered")
CAPABILITIES = ("A1", "A2", "A3", "A4", "B1", "B2", "B3", "C1", "C2")
STATUSES = ("official", "conditional", "behaviour", "unvalidated")
ROOT = Path(__file__).resolve().parents[1]


def read_episode(run_dir) -> list[dict]:
    d = Path(run_dir)
    if (d / "episode.jsonl").exists():
        text = (d / "episode.jsonl").read_text()
    elif (d / "episode.jsonl.gz").exists():
        with gzip.open(d / "episode.jsonl.gz", "rt") as f:
            text = f.read()
    else:
        raise FileNotFoundError(f"no episode.jsonl in {d}")
    out = []
    for line in text.splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:            # a line cut by a killed writer: the rest is still usable
                continue
    return out


def _json(p: Path):
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _jsonl(p: Path) -> list[dict]:
    try:
        return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    except (OSError, json.JSONDecodeError):
        return []


def find_snapshots(run_dir) -> dict:
    """Program snapshots of the match (tools/snapshot_watch.py): {seat: {"dir", "rows", "procs"}}."""
    d = Path(run_dir).resolve()
    for base in (d / "snapshots", d.parent / "snapshots", d.parent.parent / "snapshots"):
        if base.is_dir():
            out = {}
            for s in sorted(x for x in base.iterdir() if x.is_dir()):
                out[s.name] = {"dir": str(s), "rows": _jsonl(s / "snapshots.jsonl"), "procs": _jsonl(s / "procs.jsonl")}
            return out
    return {}


def link_acts(rows: list[dict]) -> tuple[dict, dict]:
    """(acts by seat, observations by seat): every accepted act with its observation, effect step and command."""
    obs: dict = {}
    acts: dict = {}
    last_cmd: dict = {}                              # seat -> the latest cmd row (an effect row follows its cmd row)
    for r in rows:
        ev = r.get("ev")
        if ev == "observe" and "obs_id" in r:
            obs.setdefault(r["seat"], {})[r["obs_id"]] = r
        elif ev == "cmd":
            last_cmd[r["seat"]] = r
        elif ev == "act_received" and r.get("act_id") is not None:
            seat = r["seat"]
            o = obs.get(seat, {}).get(r.get("obs_id_last"))
            acts.setdefault(seat, {})[r["act_id"]] = {
                "act_id": r["act_id"], "seat": seat, "entity": r.get("entity"), "k_recv": r.get("k"),
                "unit": r.get("unit"), "decision": r.get("decision"), "obs_id_last": r.get("obs_id_last"), "obs": o,
                "k_obs": o.get("k") if o else None, "view_steps": o.get("view_steps") if o else None,
                "seen": r.get("seen"), "k_effect": None, "cmd": None, "rejected": False, "dropped": None}
        elif ev == "effect":
            a = acts.get(r["seat"], {}).get(r.get("act_id"))
            if a is not None:
                c = last_cmd.get(r["seat"])
                a["k_effect"] = r.get("k")
                a["cmd"] = c.get("cmd") if c is not None and c.get("k") == r.get("k") else None
                a["rejected"] = bool(r.get("rejected"))
                if "info" in r:
                    a["info"] = r["info"]
        elif ev == "act_dropped":
            a = acts.get(r["seat"], {}).get(r.get("act_id"))
            if a is not None:
                a["dropped"] = r.get("why")
    return {s: [v[i] for i in sorted(v)] for s, v in acts.items()}, obs


class World:
    """A deterministic replay of the episode's world, stepped forward on demand (see the module text)."""

    def __init__(self, sport, rows: list[dict], build=None):
        self.sport, self.build, self.rows = sport, build, rows
        self.head = next(r for r in rows if r["ev"] == "header")
        self.cfg = header_cfg(self.head)
        self.rep = [r for r in rows if r["ev"] in REPLAYED and r["ev"] != "header"]
        end = next((r for r in self.rep if r["ev"] == "end"), None)
        self.turn = sport.protocol == "turn"
        if not self.turn:
            self.at_k: dict = {}
            for r in self.rep:
                self.at_k.setdefault(int(r["k"]), []).append(r)
            self.k_end = int(end["k"]) if end else max(self.at_k, default=0)
        self.events: dict = {}
        self.reset()

    def reset(self):
        self.m = (self.build or self.sport.build)(self.cfg)
        self.forfeits, self.retired = [], []
        self.done_k = None                           # realtime: the step whose rows were applied
        self.i = 0                                   # turn: the next row

    @property
    def k(self) -> int:
        return int(self.m.k)

    def _apply_rows(self):
        if self.done_k != self.m.k:
            for r in self.at_k.get(self.m.k, []):
                _dispatch(self.m, r, self.forfeits, self.retired)
            self.done_k = self.m.k

    def _step(self) -> bool:
        """Realtime: the rows of this step, then one step; False at the end of the match."""
        self._apply_rows()
        if self.m.phase().state == FINISHED or self.m.k >= self.k_end:
            return False
        ev = self.m.step()
        if ev:
            self.events[self.m.k] = ev
        return True

    def at(self, k: int, after: bool = False):
        k = int(k)
        if self.turn:
            if self.i:
                last = int(self.rep[self.i - 1].get("k", 0))
                if last > k or (last == k and not after):
                    self.reset()
            while self.i < len(self.rep):
                r = self.rep[self.i]
                rk = int(r.get("k", self.m.k))
                if rk > k or (rk == k and not after):
                    break
                _dispatch(self.m, r, self.forfeits, self.retired)
                self.i += 1
            return self.m
        if k < self.k or (k == self.k and self.done_k == k and not after):
            self.reset()
        while self.k < k:
            if not self._step():
                break
        if after and self.k == k:
            self._apply_rows()
        return self.m

    def run(self, fn=None):
        """To the end of the match, fn(m) after every step (turn: after every row)."""
        if self.turn:
            while self.i < len(self.rep):
                _dispatch(self.m, self.rep[self.i], self.forfeits, self.retired)
                self.i += 1
                if fn is not None:
                    fn(self.m)
            return self.m
        while self._step():
            if fn is not None:
                fn(self.m)
        return self.m

    def fork(self):
        """An independent match in the state of this one, for counterfactual play: a deep copy, or (a match that
        cannot be copied, e.g. one holding MuJoCo rollout objects) a second replay to the same point."""
        try:
            return copy.deepcopy(self.m)
        except Exception:  # noqa: BLE001
            w = World(self.sport, self.rows, self.build)
            if self.turn:
                while w.i < self.i:
                    _dispatch(w.m, w.rep[w.i], w.forfeits, w.retired)
                    w.i += 1
            else:
                w.at(self.k, after=self.done_k == self.k)
            return w.m


def load(run_dir, plugin: str | None = None, build=None) -> dict:
    """The records of one match as the sport's analysis reads them (the module text lists the keys)."""
    d = Path(run_dir)
    rows = read_episode(d)
    head = next((r for r in rows if r.get("ev") == "header"), None)
    if head is None:
        raise ValueError(f"{d}: the episode has no header")
    cfg = head["cfg"]
    seats = list(cfg["seats"])
    sides = {s: (cfg.get("sides") or {}).get(s, s) for s in seats}
    by = {name: [] for name in ROWS}
    for r in rows:
        if r.get("ev") in by:
            by[r["ev"]].append(r)
    acts, obs = link_acts(rows)
    events = [{"k": r["k"], **(e if isinstance(e, dict) else {"value": e})} for r in by["event"]
              for e in (r.get("events") or [])]
    sport = load_plugin(plugin) if plugin else None
    dt = None
    if sport is not None:
        try:
            dt = float((build or sport.build)(header_cfg(head)).dt or 0) or None
        except Exception:  # noqa: BLE001
            dt = None

    def world(build_override=None):
        if sport is None:
            raise RuntimeError("load(run_dir, plugin) without a plugin has no world()")
        return World(sport, rows, build_override or build)

    rep = {"interface": INTERFACE, "run_dir": str(d), "plugin": plugin, "sport": head.get("sport"),
           "protocol": head.get("protocol") or (sport.protocol if sport else None), "revision": head.get("revision"),
           "core_version": (head.get("versions") or {}).get("core"), "header": head, "cfg": cfg, "seats": seats,
           "sides": sides, "dt": dt, "rows": rows, **by, "has": {n: bool(by[n]) for n in DIAG}, "obs": obs,
           "acts": acts, "events": events, "final": _json(d / "final.json"),
           "replay_check": _json(d / "replay_check.json"), "local_result": _json(d / "local_result.json"),
           "snapshots": find_snapshots(d), "world": world}
    return rep


def _q(v: list, p: float):
    if not v:
        return None
    x = sorted(v)
    return x[min(len(x) - 1, max(0, math.ceil(p * len(x)) - 1))]


def linkage(rep: dict) -> dict:
    """Per seat: how completely the acts link to an observation and to an effect or a drop (the logging check)."""
    out = {}
    for seat in rep["seats"]:
        A = rep["acts"].get(seat, [])
        ids = [a["act_id"] for a in A]
        eff = [a for a in A if a["k_effect"] is not None]
        drop = [a for a in A if a["dropped"] is not None]
        lag_obs = [a["k_effect"] - a["k_obs"] for a in eff if a["k_obs"] is not None]
        lag_recv = [a["k_effect"] - a["k_recv"] for a in eff if a["k_recv"] is not None]
        out[seat] = {
            "acts": len(A), "act_ids_contiguous": ids == list(range(1, len(A) + 1)),
            "with_observation": sum(a["obs"] is not None for a in A),
            "obs_id_unknown": sum(a["obs_id_last"] is not None and a["obs"] is None for a in A),
            "before_any_observation": sum(a["obs_id_last"] is None for a in A),
            "effect": len(eff), "effect_with_cmd": sum(a["cmd"] is not None for a in eff),
            "dropped": len(drop), "dropped_by": {w: sum(a["dropped"] == w for a in drop)
                                                 for w in sorted({a["dropped"] for a in drop})},
            "unresolved": sum(a["k_effect"] is None and a["dropped"] is None for a in A),
            "both": sum(a["k_effect"] is not None and a["dropped"] is not None for a in A),
            "obs_to_effect_steps": {"median": statistics.median(lag_obs) if lag_obs else None,
                                    "p90": _q(lag_obs, 0.9), "max": max(lag_obs, default=None)},
            "recv_to_effect_steps": {"median": statistics.median(lag_recv) if lag_recv else None,
                                     "max": max(lag_recv, default=None)},
            "observations": len(rep["obs"].get(seat, {})),
        }
    return out


def c1(rep: dict) -> dict:
    """C1 (description only, framework §3): the program's reliability from the core's rows, per seat."""
    out = {}
    dt = rep.get("dt") or 0.0
    refused = {}
    for r in rep["rows"]:
        if r.get("ev") in ("refused_invalid", "refused_not_model", "refused_query"):
            refused.setdefault(r.get("seat"), {}).setdefault(r["ev"], 0)
            refused[r.get("seat")][r["ev"]] += 1
    for seat in rep["seats"]:
        A = rep["acts"].get(seat, [])
        eff = [a for a in A if a["k_effect"] is not None]
        ks = [a["k_effect"] for a in eff]
        gaps = [b - a for a, b in zip(ks, ks[1:])]
        out[seat] = {"acts": len(A), "effects": len(eff), "rejected": sum(a["rejected"] for a in eff),
                     "dropped": sum(a["dropped"] is not None for a in A), "refused": refused.get(seat, {}),
                     "first_effect_k": ks[0] if ks else None,
                     "first_effect_s": round(ks[0] * dt, 4) if ks and dt else None,
                     "effect_gap_steps": {"median": statistics.median(gaps) if gaps else None, "p90": _q(gaps, 0.9),
                                          "max": max(gaps, default=None)},
                     "observations": len(rep["obs"].get(seat, {}))}
    return out


def load_diagnoser(path):
    spec = importlib.util.spec_from_file_location("ro_sport_diagnose", path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(Path(path).resolve().parent))
    spec.loader.exec_module(mod)
    return mod


def find_diagnoser(plugin: str | None, sport: str | None, given: str | None = None):
    if given:
        return Path(given)
    for p in ([Path(plugin).resolve().parent / "diagnose.py"] if plugin else []) + \
             ([ROOT / "sports" / sport / "diagnose.py"] if sport else []):
        if p.is_file():
            return p
    return None


def check_metrics(metrics) -> list[str]:
    """The shape of metrics() (the shared interface): per seat {metric_id: {value, capability, status}}."""
    bad = []
    if not isinstance(metrics, dict):
        return ["metrics() must return {seat: {metric_id: {...}}}"]
    for seat, ms in metrics.items():
        if not isinstance(ms, dict):
            bad.append(f"{seat}: not a dict")
            continue
        for mid, v in ms.items():
            if not isinstance(v, dict) or "value" not in v:
                bad.append(f"{seat}.{mid}: needs value")
                continue
            if v.get("capability") not in CAPABILITIES:
                bad.append(f"{seat}.{mid}: capability {v.get('capability')!r} not in {CAPABILITIES}")
            if v.get("status") not in STATUSES:
                bad.append(f"{seat}.{mid}: status {v.get('status')!r} not in {STATUSES}")
    return bad


def _dump(x):
    from .diaglog import jsonable
    return json.dumps(jsonable(x))


def diagnose(rep: dict, mod=None, out: Path | None = None) -> dict:
    """Run the sport's analysis (mod: its diagnose module, or None for the core's part only) and write out/."""
    out = Path(out or Path(rep["run_dir"]) / "diag")
    out.mkdir(parents=True, exist_ok=True)
    units, claims, metrics, errors = [], [], {}, []
    if mod is not None:
        units = list(mod.units(rep))
        claims = list(mod.implied(rep, units))
        metrics = mod.metrics(units, claims)
        errors += check_metrics(metrics)
    (out / "units.jsonl").write_text("".join(_dump(u) + "\n" for u in units))
    (out / "claims.jsonl").write_text("".join(_dump(c) + "\n" for c in claims))
    fin = rep.get("final") or rep.get("local_result") or {}
    summary = {"interface": INTERFACE, "sport": rep["sport"], "revision": rep["revision"],
               "core_version": rep["core_version"], "run_dir": rep["run_dir"], "seats": rep["seats"],
               "has": rep["has"], "outcome": {k: fin.get(k) for k in ("scores", "winner", "valid_trial", "reason")
                                                if k in fin},
               "diagnoser": None if mod is None else {
                   "file": getattr(mod, "__file__", None),
                   "sha256": hashlib.sha256(Path(mod.__file__).read_bytes()).hexdigest() if getattr(
                       mod, "__file__", None) else None,
                   "validity": getattr(mod, "VALIDITY_REPORT", None)},
               "units": len(units), "claims": len(claims), "metrics": metrics, "linkage": linkage(rep),
               "c1": c1(rep), "events": len(rep["events"]), "snapshots": {
                   s: {"snapshots": len(v["rows"]), "saved": sum(1 for r in v["rows"] if r.get("tar")),
                       "procs": len(v["procs"])} for s, v in rep["snapshots"].items()},
               "errors": errors}
    (out / "summary.json").write_text(_dump(summary))
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m core.diagnose")
    ap.add_argument("plugin")
    ap.add_argument("run_dir")
    ap.add_argument("--diagnose", default=None, help="the sport's diagnose.py (default: next to PLUGIN, else "
                                                      "sports/<sport>/diagnose.py)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-sport", action="store_true", help="only the core's part (linkage, C1)")
    a = ap.parse_args(argv)
    rep = load(a.run_dir, a.plugin)
    path = None if a.no_sport else find_diagnoser(a.plugin, rep["sport"], a.diagnose)
    mod = load_diagnoser(path) if path else None
    s = diagnose(rep, mod, Path(a.out) if a.out else None)
    print(json.dumps({k: s[k] for k in ("sport", "units", "claims", "errors")} | {"diagnoser": str(path) if path
                                                                                   else None}))
    return 1 if s["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
