"""The skill contract (docs/framework_zh.md §6.3.7, §9 robot and mode rule 10): one definition of a skill API that
both modes use. The high level's act IS the skill (the platform's implementation lowers it); the low level's
deliverable implements the same call; the post-match API test measures an implementation against it.

A sport writes one SkillContract per skill (its [modes.high] contract module exports CONTRACTS = {name: contract}):

    AIM = SkillContract(
        name="aim", call="aim(x, y)",
        args={"x": {"type": "number", "min": 1, "max": 9, "unit": "m"},          # core schema fields (core/sport.py
              "y": {"type": "number", "min": -3, "max": 3, "unit": "m"}},         # check_command), in call order
        returns="one low-level command {type: throw, yaw, pitch, speed}",
        measured="the ball's first ground contact, no execution scatter",
        tolerances=(Tolerance("landing_err_m", 0.03, text="landing point within 3 cm"),),
        must_be_zero=("refused",))

Field kinds (the core's schema format, so that the high level's act schema can BE the contract's request schema):
number (min, max), vector (len, min, max for every component) and enum (values: the value is one of them);
contract-only keys the core ignores: `box` (per-component [[lo, hi], ...]), `nonzero` (a direction), `max_norm`.

A measurement (the sport's evaluator hook measures one request) is a dict of numbers: the tolerance metrics, the
counters of must_be_zero, `measured` (False: nothing to measure, e.g. no command) and anything else to report.
judge() gives the per-tolerance verdicts and the request's success; aggregate() the API test's summary.

Standard library only: the contract is read by the simulator, the evaluator, the checks and the generator alike.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Tolerance:
    """metric <= limit + rel x measurement[rel_to] (abs value of the metric when two_sided)."""

    metric: str
    limit: float
    rel: float = 0.0
    rel_to: str | None = None
    two_sided: bool = False
    text: str = ""

    def ok(self, m: dict) -> bool:
        v = m.get(self.metric)
        if not _num(v):
            return False
        v = abs(v) if self.two_sided else v
        bound = self.limit + (self.rel * float(m.get(self.rel_to, 0.0)) if self.rel_to else 0.0)
        return v <= bound + 1e-12

    def describe(self) -> dict:
        out = {"metric": self.metric, "limit": self.limit}
        if self.rel_to:
            out.update(rel=self.rel, rel_to=self.rel_to)
        if self.two_sided:
            out["two_sided"] = True
        if self.text:
            out["text"] = self.text
        return out


@dataclass(frozen=True)
class SkillContract:
    name: str  # the skill = the high level's act type = the deliverable's function
    call: str  # "aim(x, y)"
    args: dict  # request fields (core schema), in call order
    returns: str  # what an implementation returns (the low level's command)
    measured: str  # how a delivered request is measured
    tolerances: tuple = ()
    must_be_zero: tuple = ("refused",)  # measurement counters that fail the request when non-zero
    metrics: tuple = ()  # further measurement keys whose mean the summary reports
    feasible: str = ""  # why every API-test request is feasible under the real limits
    replaces: str = ""  # what a new request does to one under way (realtime skills)
    notes: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ requests
    def request_schema(self) -> dict:
        """The core schema of the skill's request: {name: {field: spec}} (the high level's act schema)."""
        return {self.name: {k: dict(v) for k, v in self.args.items()}}

    def args_of(self, req: dict) -> list:
        return [req[k] for k in self.args]

    def valid_request(self, req: dict) -> str | None:
        """None if `req` (field -> value) is within the contract's ranges, else the reason."""
        if not isinstance(req, dict):
            return "a request is an object of the call's fields"
        extra = sorted(set(req) - set(self.args) - {"type"})
        if extra:
            return f"unknown field(s) {extra}"
        for k, f in self.args.items():
            if k not in req:
                return f"{self.name} needs {k}"
            bad = _field_problem(k, f, req[k])
            if bad:
                return bad
        return None

    # ------------------------------------------------------------------ verdicts
    def judge(self, m: dict) -> dict:
        """Per-tolerance verdicts (ok_<metric>) and the request's success."""
        measured = bool(m.get("measured", True))
        ok = {f"ok_{t.metric}": measured and t.ok(m) for t in self.tolerances}
        clean = all(not m.get(c) for c in self.must_be_zero)
        ok["success"] = bool(measured and clean and all(ok.values()))
        return ok

    def aggregate(self, rows: list[dict]) -> dict:
        """The API test's summary of judged rows (each: the measurement + judge() + skill counters)."""
        n = len(rows)
        out = {"n": n, "success": sum(bool(r.get("success")) for r in rows)}
        out["success_rate"] = round(out["success"] / n, 4) if n else 0.0
        out["measured"] = sum(bool(r.get("measured", True)) for r in rows)
        for t in self.tolerances:
            out[f"pass_{t.metric}"] = round(sum(bool(r.get(f"ok_{t.metric}")) for r in rows) / n, 4) if n else 0.0
        for k in [t.metric for t in self.tolerances] + list(self.metrics):
            vals = sorted(abs(float(r[k])) for r in rows if r.get("measured", True) and _num(r.get(k)))
            if vals:
                out[k] = {
                    "mean": round(sum(vals) / len(vals), 5),
                    "median": round(_q(vals, 0.5), 5),
                    "p90": round(_q(vals, 0.9), 5),
                    "max": round(vals[-1], 5),
                }
        for c in self.must_be_zero:
            out[f"{c}_total"] = sum(int(r.get(c) or 0) for r in rows)
        for c in ("skill_errors", "skill_timeouts"):
            out[c] = sum(int(r.get(c) or 0) for r in rows)
        return out

    def describe(self, deliverable: dict | None = None) -> dict:
        """The contract as data: /spec (skill_contract), the report, the task's instructions."""
        out = {
            "skill": self.name,
            "call": self.call,
            "request": self.request_schema()[self.name],
            "returns": self.returns,
            "measured": self.measured,
            "tolerances": [t.describe() for t in self.tolerances],
            "success": "every tolerance met"
            + (f" and no {', no '.join(self.must_be_zero)}" if self.must_be_zero else ""),
        }
        for k in ("feasible", "replaces"):
            if getattr(self, k):
                out[k] = getattr(self, k)
        if self.notes:
            out["notes"] = dict(self.notes)
        if deliverable:
            out["deliverable"] = dict(deliverable)
        return out


# ------------------------------------------------------------------ helpers
def _num(v) -> bool:
    return not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v)


def _q(vals: list[float], q: float) -> float:
    if not vals:
        return 0.0
    i = q * (len(vals) - 1)
    lo, hi = math.floor(i), math.ceil(i)
    return vals[lo] + (vals[hi] - vals[lo]) * (i - lo)


def _field_problem(name: str, f: dict, v) -> str | None:
    t = f.get("type", "number")
    if t == "number":
        if not _num(v):
            return f"{name} must be a finite number"
        if not f.get("min", -math.inf) <= v <= f.get("max", math.inf):
            return f"{name} must be in [{f.get('min')}, {f.get('max')}]"
        return None
    if t == "vector":
        n = f.get("len")
        if not isinstance(v, (list, tuple)) or (isinstance(n, int) and len(v) != n) or not all(_num(x) for x in v):
            return f"{name} must be a list of {n} finite numbers"
        lo, hi = f.get("min", -math.inf), f.get("max", math.inf)
        box = f.get("box") or [[lo, hi]] * len(v)
        for i, (x, (a, b)) in enumerate(zip(v, box)):
            if not (max(a, lo) <= x <= min(b, hi)):
                return f"{name}[{i}] must be in [{max(a, lo)}, {min(b, hi)}]"
        norm = math.sqrt(sum(x * x for x in v))
        if f.get("nonzero") and norm < 1e-9:
            return f"{name} must be non-zero"
        if _num(f.get("max_norm")) and norm > f["max_norm"]:
            return f"|{name}| must be at most {f['max_norm']}"
        return None
    if t == "enum":
        if v not in f.get("values", []):
            return f"{name} must be one of {f.get('values', [])}"
        return None
    return f"{name}: field type {t!r} is not supported by a skill contract (number, vector, enum)"
