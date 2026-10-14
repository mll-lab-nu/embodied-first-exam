"""The post-match evaluator of a low-level skill (docs/framework_zh.md §6.3.7, §9 robot and mode rule 10). It runs in
the evaluation container that tools/skill_eval.py starts (no network, read-only, the skill mounted read-only at
/app/output/skill, the simulator readable by root only, the skill in its own process as `nobody`):

    cd /srv/sim && python3 -m skilleval.evaluate --sport-dir sport --impl skill --skill /app/output/skill
    python3 -m skilleval.evaluate --sport-dir sport --impl platform              # our implementation (reference row)
    python3 -m skilleval.evaluate --sport-dir sport --impl skill --skill DIR --checks   # + the contract checks
    python3 -m skilleval.evaluate --sport-dir sport --probe --skill DIR          # the isolation probe (skilleval/probe/)

  1 API test          every hidden request (sport.toml [modes.low.cases] hidden) through the sport's hook
                      api_case(case, skill) -> measurement; the contract judges it (skilleval/contract.py); summary
  2 competition test  the sport's hook competition_match(skill, seed) for each of its COMPETITION_SEEDS: our fixed
                      reference strategy on the implementation; summary (success rate, means)
  3 determinism       the first cases again in a fresh process: the same answers
  4 checks (--checks) the contract's request schema = the high level's act schema (the core's `entity` aside);
                      every case's request is valid

The sport's evaluator module ([modes.low] evaluator) provides:
    CONTRACTS                 {skill: SkillContract} (usually the [modes.high] contract module's)
    skill_spec() -> dict      the `spec` keyword every call receives (the low level's game spec part)
    platform() -> object      our implementation, the same functions as the deliverable (in process)
    api_case(case, skill) -> dict           one request through skill.call(...): the measurement
    competition_match(skill, seed) -> dict  optional: {"seed", "success", ...numbers}
    COMPETITION_SEEDS         optional: the seeds of the competition test
    fallback(seat, match)     optional: the low-level command a failed skill call lowers to (skilleval/layer.py)
The report is one JSON object, printed after the line `REPORT` (tools/skill_eval.py reads it) or written to --out.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
import tomllib
from pathlib import Path

from . import VERSION
from . import cases as cases_mod
from .sandbox import InProcessSkill, SkillError, SkillProcess
from .skillhost import files_sha

DETERMINISM_CASES = 5


def load_hooks(sport_dir: Path, rel: str):
    for p in (str(sport_dir), str(sport_dir.parent)):
        if p not in sys.path:
            sys.path.insert(0, p)
    spec = importlib.util.spec_from_file_location(Path(rel).stem, sport_dir / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def tree_sha(path: Path) -> str | None:
    """The skill's identity: the same hash the skill in the loop records for every call (skillhost.files_sha)."""
    return files_sha(path)


def skill_fields(act):
    """An act type of the high level's schema without the core's `entity` (core/sport.py check_command: which of the
    seat's robots the act is for, one of Match.entities): what the contract's request schema must equal."""
    return {k: v for k, v in act.items() if k != "entity"} if isinstance(act, dict) else act


class Harness:
    def __init__(self, sport_dir: Path, impl: str, skill_dir: Path | None):
        self.sport_dir = Path(sport_dir).resolve()
        self.decl = tomllib.loads((self.sport_dir / "sport.toml").read_text())
        self.lo = self.decl["modes"]["low"]
        self.dl = self.lo["deliverable"]
        self.fn = Path(self.dl["path"]).stem
        self.hooks = load_hooks(self.sport_dir, self.lo["evaluator"])
        self.contracts = self.hooks.CONTRACTS
        self.spec = self.hooks.skill_spec()
        self.impl, self.skill_dir = impl, skill_dir
        self.tl = {k: float(v) for k, v in (self.dl.get("time_limits_s") or {}).items()}

    def new_skill(self):
        if self.impl == "platform":
            return InProcessSkill(self.hooks.platform(), context={"spec": self.spec})
        return SkillProcess(
            self.skill_dir,
            self.fn,
            context={"spec": self.spec},
            timeouts=self.tl,
            load_timeout_s=self.tl.get("load", 30.0),
        )

    def deliverable_problem(self) -> str | None:
        if self.impl == "platform":
            return None
        if self.skill_dir is None or not (Path(self.skill_dir) / f"{self.fn}.py").is_file():
            return f"no {self.fn}.py in {self.skill_dir}: nothing to evaluate (API test 0, competition test 0)"
        s = self.new_skill()
        try:
            if not s.alive:
                return f"the skill does not load: {(s.errors or ['?'])[-1][-400:]}"
            if not s.has(self.fn):
                return f"{self.fn}.py defines no function {self.fn}"
        finally:
            s.close()
        return None

    # ------------------------------------------------------------------ 1 API test
    def run_cases(self, cases: list[dict]) -> tuple[list[dict], list]:
        fresh = self.dl.get("memory", "per_run") == "per_case"
        rows, skill, log = [], None, []
        for case in cases:
            if skill is None or fresh:
                if skill is not None:
                    log += skill.log
                    skill.close()
                skill = self.new_skill()
            c = self.contracts[case.get("skill", self.fn)]
            before = skill.counters()
            try:
                m = dict(self.hooks.api_case(case, skill)) if skill.alive else {"measured": False, "skill_dead": 1}
            except SkillError as e:
                m = {"measured": False, f"skill_{e.kind}": 1}
            after = skill.counters()
            m.update({k: after[k] - before[k] for k in ("skill_errors", "skill_timeouts")})
            m.update(c.judge(m))
            rows.append({"id": case["id"], **m})
        if skill is not None:
            log += skill.log
            skill.close()
        return rows, log

    def api_test(self, which: str) -> tuple[dict, list[dict], list[dict]]:
        cs = self.lo["cases"]
        cases = []
        if which in ("hidden", "all"):
            cases += cases_mod.load(self.sport_dir / cs["hidden"])
        if which in ("public", "all"):
            cases += cases_mod.load(self.sport_dir / cs["public"])
        rows, log = self.run_cases(cases)
        by_skill = {}
        for name, c in self.contracts.items():
            mine = [r for r, case in zip(rows, cases) if case.get("skill", self.fn) == name]
            if mine:
                by_skill[name] = c.aggregate(mine)
        summary = by_skill[self.fn] if list(by_skill) == [self.fn] else {"by_skill": by_skill}
        summary["set"] = which
        return summary, rows, cases

    def determinism(self, cases: list[dict]) -> dict:
        """The first cases twice, each time in fresh processes: the same answers (rule 10: deterministic)."""
        k = min(DETERMINISM_CASES, len(cases))
        if k == 0 or self.impl == "platform":
            return {"checked": 0, "deterministic": True}
        _, log1 = self.run_cases(cases[:k])
        _, log2 = self.run_cases(cases[:k])
        return {"checked": k, "calls": len(log1), "deterministic": log1 == log2}

    # ------------------------------------------------------------------ 2 competition test
    def competition(self) -> tuple[dict, list[dict]]:
        f = getattr(self.hooks, "competition_match", None)
        if f is None:
            return {"n": 0, "note": "the sport has no competition hook"}, []
        rows = []
        for seed in getattr(self.hooks, "COMPETITION_SEEDS", [1, 2, 3, 4]):
            skill = self.new_skill()
            try:
                r = dict(f(skill, seed))
            except SkillError as e:
                r = {"seed": seed, "success": 0, "skill_failed": e.kind}
            except Exception as e:  # noqa: BLE001  (the match could not be played with this implementation)
                r = {"seed": seed, "success": 0, "match_error": f"{type(e).__name__}: {e}"[:300]}
            finally:
                skill.close()
            r.update(seed=seed, **{k: v for k, v in skill.counters().items() if k != "skill_calls"})
            rows.append(r)
        n = len(rows)
        out = {"n": n, "success": sum(bool(r.get("success")) for r in rows)}
        out["success_rate"] = round(out["success"] / n, 4) if n else 0.0
        for k in sorted(
            {
                k
                for r in rows
                for k, v in r.items()
                if isinstance(v, (int, float)) and k not in ("seed", "success") and not isinstance(v, bool)
            }
        ):
            vals = [float(r[k]) for r in rows if isinstance(r.get(k), (int, float))]
            out[f"mean_{k}"] = round(sum(vals) / len(vals), 4)
        g = getattr(self.hooks, "competition_summary", None)
        if g is not None:
            out.update(g(rows))
        return out, rows

    # ------------------------------------------------------------------ 4 checks
    def checks(self, cases: list[dict]) -> list[dict]:
        from core.episode import load_plugin
        from core.sport import MatchConfig

        out = []
        plugin = load_plugin(str(self.sport_dir / "plugin.py"))
        fmt_name, fmt = next(iter(self.decl["formats"].items()))
        seats = tuple(fmt["seats"])
        cfg = MatchConfig(
            sport=self.decl["sport"]["name"], format=fmt_name, seats=seats, seed=1, first=seats[0], action_level="high"
        )
        m = plugin.build(cfg)
        high = plugin.action_layer("high").schema(m, seats[0])
        for name, c in self.contracts.items():
            want, got = c.request_schema()[name], skill_fields(high.get(name))
            out.append(
                {
                    "name": f"contract {name}: request schema = the high level's act schema (the core's entity aside)",
                    "ok": got == want,
                    "detail": {"contract": want, "high": got},
                }
            )
        bad = [c["id"] for c in cases if self.contracts[c.get("skill", self.fn)].valid_request(c["request"])]
        out.append({"name": "every case's request is valid under the contract", "ok": not bad, "detail": bad[:5]})
        return out


def _alive(pid: int) -> bool:
    """The process exists and is not a zombie."""
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        return False


def probe(skill_dir: Path, targets: dict) -> dict:
    """The isolation probe: skilleval/probe/probe.py tries each target; nothing may succeed."""
    s = SkillProcess(skill_dir, "probe", timeouts={"probe": 20})
    try:
        got = s.call("probe", targets) if s.alive else {"load": s.errors}
    except SkillError as e:
        got = {"error": str(e)}
    finally:
        s.close()
    if isinstance(got, dict) and got.get("survivor_pid"):      # its detached process must be gone with the skill
        got["survives_close"] = _alive(int(got["survivor_pid"]))
    leaks = sorted(k for k, v in got.items() if v is True) if isinstance(got, dict) else ["?"]
    return {
        "ok": isinstance(got, dict) and "error" not in got and "load" not in got and not leaks,
        "leaks": leaks,
        "results": got,
        "dropped_to_nobody": os.geteuid() == 0,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m skilleval.evaluate")
    ap.add_argument("--sport-dir", required=True)
    ap.add_argument("--impl", default="skill", choices=["skill", "platform"])
    ap.add_argument("--skill", help="the skill directory (default /app/output/skill)", default="/app/output/skill")
    ap.add_argument("--label", default=None, help="what is evaluated (player, reference, boundary, ...)")
    ap.add_argument("--set", default="hidden", choices=["hidden", "public", "all"])
    ap.add_argument("--no-competition", action="store_true")
    ap.add_argument("--checks", action="store_true")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--isolation", default="none (in-process run: not an official evaluation)")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    t0 = time.time()
    sport_dir = Path(a.sport_dir).resolve()
    decl = tomllib.loads((sport_dir / "sport.toml").read_text())
    report = {
        "evaluator": f"skilleval/{VERSION}",
        "sport": decl["sport"]["name"],
        "revision": decl["sport"]["revision"],
        "isolation": a.isolation,
        "t0": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if a.probe:
        lo = decl["modes"]["low"]
        targets = {
            "read_sport_toml": str(sport_dir / "sport.toml"),
            "read_hidden_cases": str(sport_dir / lo["cases"]["hidden"]),
            "read_evaluator": str(sport_dir / lo["evaluator"]),
            "list_simulator": str(sport_dir.parent),
            "write_skill_dir": str(Path(a.skill) / "probe_write.txt"),
            "write_verifier_logs": "/logs/verifier/probe_write.txt",   # the agent-visible log directory (Harbor: 777)
            "write_report_dir": str(Path(a.out).parent / "probe_write.txt") if a.out else "/var/lib/skilleval/probe_write.txt",
        }
        report.update(probe=probe(Path(a.skill), targets))
        report["valid"] = report["probe"]["ok"]
    else:
        h = Harness(sport_dir, a.impl, Path(a.skill) if a.impl == "skill" else None)
        tk = tomllib.loads((sport_dir / h.lo["toolkit"]).read_text())["toolkit"]
        report.update(
            impl=a.impl,
            label=a.label or a.impl,
            skill_sha256=tree_sha(Path(a.skill)) if a.impl == "skill" else None,
            deliverable=h.dl,
            toolkit={"id": tk["id"], "version": tk["version"]},
            contracts={k: c.describe() for k, c in h.contracts.items()},
        )
        why = h.deliverable_problem()
        if why:
            report.update(
                valid=False, reason=why, api_test={"success_rate": 0.0}, competition_test={"success_rate": 0.0}
            )
        else:
            api, rows, cases = h.api_test(a.set)
            report.update(valid=True, api_test=api, determinism=h.determinism(cases), api_rows=rows)
            if not a.no_competition:
                comp, crows = h.competition()
                report.update(competition_test=comp, competition_rows=crows)
            if a.checks:
                report["checks"] = h.checks(cases)
        ref = sport_dir / str(h.lo.get("reference_results", ""))
        if h.lo.get("reference_results") and ref.is_file():
            report["reference_results"] = json.loads(ref.read_text())
    report["seconds"] = round(time.time() - t0, 1)
    text = json.dumps(report, sort_keys=True, default=float)
    if a.out:
        Path(a.out).write_text(text)
    sys.stdout.write("\nREPORT\n" + text + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
