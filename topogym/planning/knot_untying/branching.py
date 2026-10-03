"""Decision search on one live Env, with complete checkpoints and an accepted action prefix.

Temporary crossing increases and tight curls may continue within a search budget.
Failure downstream still retries earlier decisions. Resume rebuilds the frozen instance and
replays actions; a pickle is controller bookkeeping, not a portable physics checkpoint.
Only load locally trusted checkpoint files. Independent replay is still required.
"""
from __future__ import annotations

import copy
import json
import pickle
import time

import numpy as np

from . import robot_oracle as oracle
from .cli import validate_parameters
from topogym.utils.io import write_json_atomic

ROUTE_KEYS = ("lift", "hold", "direction", "straighten")
ARG_KEYS = ("close", "speed", "max_pull", "full_pull", "end_offset")
CANDIDATES = {
    "withdraw": [{}, dict(full_pull=True, max_pull=.55), dict(full_pull=True, max_pull=.65),
                 dict(full_pull=True, max_pull=.55, direction="tangent"),
                 dict(full_pull=True, max_pull=.55, direction="away")],
    "straighten": [{}, dict(end_offset=.05), dict(straighten=.8)],
    "carry": [{}],
}
SESSION_FIELDS = ("n_steps", "physics_steps", "sim_time_s", "last_step_ticks", "_reward", "episode_end", "episode_done")
RUNNER_FIELDS = ("q", "g", "bias", "full_q", "grasps", "grasp_turn", "decisions", "log", "lines")


def validate_candidate(candidate):
    if not isinstance(candidate, dict) or set(candidate)-set(ROUTE_KEYS+ARG_KEYS):
        raise ValueError("candidate must be an object containing only route and grasp parameters")
    validate_parameters(candidate)
    if "hold" in candidate and candidate["hold"] not in ("far", "over"):
        raise ValueError("hold must be far or over")
    if "direction" in candidate and candidate["direction"] not in ("tangent", "away"):
        raise ValueError("direction must be tangent or away")
    for key, upper in (("lift", .1), ("straighten", .95)):
        if key in candidate and (isinstance(candidate[key], bool) or not isinstance(candidate[key], (float, int))
                                 or not 0 < candidate[key] <= upper):
            raise ValueError(f"{key} must be in (0, {upper}]")
    return candidate


class Branching:
    def __init__(self, args):
        self.args = args
        self.r = oracle.Runner(args)
        self.base_cfg = dict(oracle.TIERS[args.variation])
        self.base_args = {k: getattr(args, k) for k in ARG_KEYS}
        self.attempts, self.selection = [], []
        self.control = args.output/"control"
        self.control.mkdir()
        (args.output/"checkpoints").mkdir()
        self.start = 1
        self.backtracks = 0
        if args.resume:
            try:
                self.resume(pickle.loads(args.resume.read_bytes()))
            except BaseException:
                self.r.session.close()
                raise

    def resume(self, saved):
        r, s = self.r, self.r.session
        if saved.get("schema_version") != 2 or saved.get("instance_identity") != r.identity:
            raise ValueError("checkpoint schema or frozen instance identity differs; cannot resume")
        if saved["action_layout"] != s.action_layout:
            raise ValueError("checkpoint action layout differs")
        actions = np.asarray(saved["actions"], dtype=np.float32)
        ticks = np.asarray(saved["ticks"])
        if (actions.ndim != 2 or actions.shape[1] != s.action_dim or ticks.shape != (len(actions),)
                or not np.isfinite(actions).all() or ticks.dtype.kind not in "iu"
                or np.any(ticks <= 0) or np.any(ticks > s.physics_substeps)):
            raise ValueError("invalid checkpoint action/tick ledger")
        if saved["decision"] < 1 or len(saved["runner"]["log"]) != len(actions):
            raise ValueError("invalid checkpoint decision or log length")
        print(f"RESUME replaying {len(actions)} actions to decision {saved['decision']}", flush=True)
        for row, count in zip(actions, ticks):
            if s.step(row, _physics_steps=int(count)):
                raise RuntimeError(f"resume ended before the decision checkpoint: {s.episode_end}")
        line_error = float(np.max(np.abs(r.line()-saved["centerline"])))
        joint_error = float(np.max(np.abs(s.joint_positions()-saved["joint_positions"])))
        write_json_atomic(self.args.output/"resume.json", dict(actions=len(actions), physics_steps=s.physics_steps,
                          centerline_error_m=line_error, joint_error=joint_error))
        if line_error > .0002 or joint_error > .0002:
            raise RuntimeError("resume replay drift exceeds 0.2 mm / 0.2 mrad")
        for name, value in saved["runner"].items():
            setattr(r, name, copy.deepcopy(value))
        self.attempts = copy.deepcopy(saved["attempts"])
        self.selection = copy.deepcopy(saved["selection"])
        self.start = saved["decision"]
        self.base_cfg, self.base_args = saved["base_cfg"], saved["base_args"]
        self.backtracks = saved["backtracks"]
        print(f"RESUMED at {s.sim_time_s:.3f}s: {len(r.crossings())} crossings", flush=True)

    def checkpoint(self, k):
        r, s = self.r, self.r.session
        r.env._checkpoint_current()  # required by history_storage='segment'
        state = {name: copy.deepcopy(getattr(r, name, None)) for name in RUNNER_FIELDS}
        saved = dict(schema_version=2, decision=k, instance_identity=r.identity,
                     action_layout=s.action_layout, actions=np.asarray(s._recording, np.float32).reshape(-1, s.action_dim),
                     ticks=np.asarray(s._recorded_ticks, np.int64), centerline=r.line(), joint_positions=s.joint_positions(),
                     attempts=self.attempts, selection=self.selection, runner=state,
                     base_cfg=self.base_cfg, base_args=self.base_args, backtracks=self.backtracks)
        path = self.args.output/"checkpoints"/f"d{k}_a{len(self.attempts)}.pkl"
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(pickle.dumps(saved, protocol=pickle.HIGHEST_PROTOCOL))
        temporary.replace(path)
        write_json_atomic(self.args.output/"checkpoints/latest.json", dict(path=path.name, decision=k))
        return dict(ref=dict(r.env._info()["state_ref"]), runner=state, selection=len(self.selection),
                    session=dict({name: copy.deepcopy(getattr(s, name)) for name in SESSION_FIELDS},
                                 recording=len(s._recording), ticks=len(s._recorded_ticks), targets=s._targets.copy()))

    def restore(self, mark):
        r, s = self.r, self.r.session
        r.env.privileged.rewind_to(mark["ref"])
        for name, value in mark["runner"].items():
            setattr(r, name, copy.deepcopy(value))
        m = mark["session"]
        for name in SESSION_FIELDS:
            setattr(s, name, copy.deepcopy(m[name]))
        del s._recording[m["recording"]:]
        del s._recorded_ticks[m["ticks"]:]
        s._targets = m["targets"].copy()
        del self.selection[mark["selection"]:]
        self.backtracks += 1

    def tight_curl(self, line):
        from .route_rule import passes
        spans = [abs(a-b) for a, _, b in passes(self.r.crossings(line), self.r.stations)]
        return bool(spans and min(spans) < self.args.tight_curl_m)

    def progress(self, record):
        """Count operations since a new crossing minimum along this accepted prefix.

        Recompute from the prefix so rewind/resume cannot inherit a rejected future.
        A 4 -> 5 -> 4 oscillation does not replenish the exploration budget.
        """
        best, stagnant = None, 0
        for row in [*self.r.decisions, record]:
            if "crossings_before" not in row or "crossings_after" not in row:
                continue
            if best is None:
                best = row["crossings_before"]
            if row["crossings_after"] < best:
                best, stagnant = row["crossings_after"], 0
            else:
                stagnant += 1
        return best, stagnant

    def attempt(self, k, kind, candidate, before):
        validate_candidate(candidate)
        r = self.r
        cfg = {**self.base_cfg, **{x: v for x, v in candidate.items() if x in ROUTE_KEYS}}
        for name in ARG_KEYS:
            setattr(self.args, name, candidate.get(name, self.base_args[name]))
        if kind == "carry":
            record = r.carry(cfg)
        elif kind == "straighten":
            record = r.straighten(k, cfg)
        else:
            from .route_rule import choose
            action = choose(r.line(), r.stations, r.crossings(), r.length, cfg["hold"], cfg["direction"])
            if action is None:
                raise RuntimeError("no under-crossing to withdraw")
            record = dict(r.withdraw(k, action, cfg), crossings_before=before)
        after = record["crossings_after"]
        flags = []
        if after >= before:
            flags.append("crossings_not_reduced")
        if kind == "straighten" and after and self.tight_curl(r.line()):
            flags.append("tight_curl_after_spread")
        best, stagnant = self.progress(record)
        record.update(heuristic_flags=flags, best_crossings=best, nonprogress_decisions=stagnant)
        if stagnant > self.args.max_nonprogress_decisions:
            return record, (f"search nonprogress budget exhausted ({stagnant} > "
                            f"{self.args.max_nonprogress_decisions}); best crossings={best}")
        return record, None

    def candidates(self, k, kind):
        seen = set()
        for candidate in CANDIDATES[kind]:
            key = json.dumps({**self.base_cfg, **self.base_args, **candidate}, sort_keys=True)
            if key not in seen:
                seen.add(key)
                yield candidate

    def extra_candidates(self, k, kind):
        if k != self.start:
            return  # Exhaust a child before waiting, so its parent can try a longer pull.
        deadline = time.monotonic()+3600*self.args.wait_hours
        try:
            while time.monotonic() < deadline:
                write_json_atomic(self.control/"waiting.json", dict(decision=k, kind=kind, tried=self.attempts))
                incoming = self.control/"next.json"
                while time.monotonic() < deadline and not incoming.exists():
                    time.sleep(min(5., max(0., deadline-time.monotonic())))
                if not incoming.exists():
                    break
                archive = self.control/f"next_{time.time_ns()}.json"
                incoming.rename(archive)
                try:
                    candidates = json.loads(archive.read_text())
                    if not isinstance(candidates, list):
                        raise ValueError("control/next.json must contain a list")
                    for candidate in candidates:
                        validate_candidate(candidate)
                except (ValueError, TypeError) as error:
                    write_json_atomic(self.control/"invalid.json", dict(file=archive.name, error=str(error)))
                    continue
                (self.control/"waiting.json").unlink(missing_ok=True)
                yield from candidates
        finally:
            (self.control/"waiting.json").unlink(missing_ok=True)

    def kind(self, crossings):
        if self.base_cfg["kind"] == "carry":
            return "carry"
        from .route_rule import only_local_loops
        last = self.r.decisions[-1] if self.r.decisions else None
        reduced = last and 0 < last["crossings_after"] < last["crossings_before"]
        spread = only_local_loops(crossings, self.r.stations) or reduced
        return "straighten" if spread and (not last or last["kind"] != "straighten") else "withdraw"

    def choices(self, k, crossings):
        """Try both physical primitives, with the existing rule choosing priority only.

        Interleave parameter candidates so one primitive cannot exhaust the node
        before the other is tried. Wait for operator additions only after both.
        """
        preferred = self.kind(crossings)
        kinds = [preferred] if preferred == "carry" else [preferred, "straighten" if preferred == "withdraw" else "withdraw"]
        pending = {kind: iter(self.candidates(k, kind)) for kind in kinds}
        while pending:
            for kind, candidates in list(pending.items()):
                try:
                    candidate = next(candidates)
                except StopIteration:
                    del pending[kind]
                    continue
                yield kind, candidate
        for candidate in self.extra_candidates(k, preferred):
            yield preferred, candidate

    def search(self, k):
        r = self.r
        crossings = r.crossings()
        if not crossings:
            deadline = r.session.sim_time_s+self.args.settle
            while r.session.sim_time_s < deadline:
                r.step("final_settle")
            return False  # geometric completion without native success is not a solution
        if k > self.args.max_decisions or len(self.attempts) >= self.args.max_attempts:
            return False
        before = len(crossings)
        mark = self.checkpoint(k)
        for n, (kind, candidate) in enumerate(self.choices(k, crossings)):
            if len(self.attempts) >= self.args.max_attempts:
                break
            started = time.time()
            row = dict(decision=k, kind=kind, candidate=candidate, n=n,
                       t0=r.session.sim_time_s, crossings_before=before, result="running")
            self.attempts.append(row)
            self.dump("running")
            try:
                record, reason = self.attempt(k, kind, candidate, before)
                row.update(crossings_after=record["crossings_after"], stopped=record.get("stopped"),
                           heuristic_flags=record.get("heuristic_flags", []),
                           best_crossings=record.get("best_crossings"),
                           nonprogress_decisions=record.get("nonprogress_decisions"))
                if reason is None:
                    r.decisions.append(record)
                    self.selection.append(dict(decision=k, kind=kind, candidate=candidate))
                    row["result"] = "accepted_pending_downstream"
                    r.dump(partial=True)
                    self.dump("running")
                    self.search(k+1)  # returns only on exhaustion; Solved propagates
                    reason = "downstream candidates exhausted or terminal stability not reached"
            except oracle.Solved:
                row.update(result="solved_path", t1=r.session.sim_time_s, wall_s=time.time()-started)
                if not any(x["decision"] == k for x in self.selection):
                    self.selection.append(dict(decision=k, kind=kind, candidate=candidate))
                raise
            except Exception as error:
                reason = f"{type(error).__name__}: {error}"
            row.update(result="rejected", reason=reason, t1=r.session.sim_time_s, wall_s=time.time()-started)
            print("ATTEMPT", json.dumps(row), flush=True)
            self.restore(mark)
            r.dump(partial=True)
            self.dump("running")
        return False

    def run(self):
        result = "unsolved"
        try:
            self.search(self.start)
        except oracle.Solved:
            result = "solved"
            self.r.decisions.append(dict(kind="episode_end", t=self.r.session.sim_time_s, episode_end="success"))
            print("SOLVED at t =", self.r.session.sim_time_s, flush=True)
        except Exception as error:
            result = f"{type(error).__name__}: {error}"
            self.r.decisions.append(dict(kind="error", error=result))
            print("ERROR", result, flush=True)
        self.dump(result)
        self.r.dump(partial=False)
        return result == "solved" and bool(self.r.task.result.task_success)

    def dump(self, result=None):
        write_json_atomic(self.args.output/"branching.json", dict(variation=self.args.variation,
            instance=str(self.args.instance), result=result, base_route=self.base_cfg, base_args=self.base_args,
            search_policy=dict(revision="bounded_nonmonotonic_v1", tight_curl_is_diagnostic=True,
                               max_nonprogress_decisions=self.args.max_nonprogress_decisions,
                               max_decisions=self.args.max_decisions, max_attempts=self.args.max_attempts),
            selection=self.selection, attempts=self.attempts, backtracks=self.backtracks,
            independent_replay_required=True))
