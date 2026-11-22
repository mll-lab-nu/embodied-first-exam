"""Persistent adaptation rounds and a one-way submission seal; trusted operator only."""

import base64
import hashlib
import json
from pathlib import Path
import secrets
import time
from ..public.model import (
    DT,
    HORIZON,
    TASK_VERSION,
    SCORE_VERSION,
    SETTLE_TIME,
    SUCCESS_POINTS,
    TIME_BONUS_POINTS,
    ORACLE_TIME_RELAXATION,
    INITIAL_XY_RANGE,
    INITIAL_HEIGHT_RANGE,
    PAD_XY_RANGE,
    MIN_TRAVEL,
)
from ..public.policy import DEFAULT, validate
from .simulation import rollout
from .rendering import STYLE, WIDTH, HEIGHT, FPS
from .oracle import prepare_bank, load_bank, validate_cases
from . import ablation as A

OBS_FIELDS = {
    "t",
    "position",
    "velocity",
    "quaternion",
    "omega",
    "specific_force",
    "rotor_rpm",
    "rotor_command",
    "pad_position",
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def public_feedback(value, folder):
    if set(value) != {"schema", "observations", "frames"} or value["schema"] != "landing-feedback/2":
        raise ValueError("Unexpected feedback schema")
    import math

    lengths = {
        "position": 3,
        "pad_position": 3,
        "velocity": 3,
        "quaternion": 4,
        "omega": 3,
        "specific_force": 3,
        "rotor_rpm": 4,
        "rotor_command": 4,
    }
    for row in value["observations"]:
        if set(row) != OBS_FIELDS or not math.isfinite(row["t"]):
            raise ValueError("Unexpected sensor fields")
        for key, n in lengths.items():
            if len(row[key]) != n or not all(type(x) in (int, float) and math.isfinite(x) for x in row[key]):
                raise ValueError("Unexpected sensor values")
    images = []
    for i, frame in enumerate(value["frames"]):
        if frame != {"time_s": float(i), "name": f"frame-{i:02d}.jpg"}:
            raise ValueError("Unexpected frame manifest")
        b = (folder / frame["name"]).read_bytes()
        images.append(
            {
                "time_s": frame["time_s"],
                "mime_type": "image/jpeg",
                "base64": base64.b64encode(b).decode(),
                "sha256": hashlib.sha256(b).hexdigest(),
            }
        )
    return {"observations": value["observations"], "images": images}


class Session:
    def __init__(self, root, residual_path, *, bank=None, render=True, oracle_workers=4, wall_clock_s=3600):
        self.root = Path(root)
        self.residual_path = Path(residual_path)
        self.render = render
        self.stopping = False   # set (signal-safe) by the service when the agent's time is up: no further case runs
        if (self.root / "state.json").exists():
            self.state = json.loads((self.root / "state.json").read_text())
            if self.state.get("task_version") != TASK_VERSION:
                raise ValueError("Session task version changed")
            if self.state["residual_sha256"] != hashlib.sha256(self.residual_path.read_bytes()).hexdigest():
                raise ValueError("Evaluator asset changed")
            if self.state.get("render_style") != (STYLE if render else None):
                raise ValueError("Session rendering style changed")
            if self.state["render"] != render:
                raise ValueError("Session rendering configuration changed")
            if any(r["status"] == "running" for r in self.state["rounds"]):
                if (self.root.parent / "cutoff.json").exists():
                    # the service restarted after the agent's time was up: that round could never be selected
                    for r in self.state["rounds"]:
                        if r["status"] == "running":
                            r["status"] = "aborted_at_cutoff"
                else:
                    self.state["infrastructure_error"] = True
                self.persist()
        else:
            if self.root.exists():
                # a start that crashed before its state was written (during the reference search): set it aside
                self.root.rename(self.root.with_name(f"{self.root.name}-incomplete-{time.time_ns()}"))
            self.root.mkdir(parents=True, mode=0o700, exist_ok=False)
            if bank is None:
                # The residual stays fixed within adaptation. Held-out tests change initial conditions/noise.
                scale = 1.0  # Paper-weight track: randomize task placement, not the released dynamics.
                bank = {
                    "adaptation": [{"seed": secrets.randbits(31), "scale": scale} for _ in range(3)],
                    "held_out": [{"seed": secrets.randbits(31), "scale": scale} for _ in range(6)],
                }
            validate_cases(bank)
            # Freeze every reference before the agent clock or deployment API starts.
            oracle_sha256 = prepare_bank(bank, self.residual_path, self.root / "oracle", workers=oracle_workers)
            self.state = {
                "schema": "landing-session/2",
                "task_version": TASK_VERSION,
                "bank": bank,
                "oracle_bank_sha256": oracle_sha256,
                "rounds": [],
                "sealed": False,
                "render": render,
                "render_style": STYLE if render else None,
                "max_rounds": 3,
                "deadline": time.time() + wall_clock_s,
                "infrastructure_error": False,
                "residual_sha256": hashlib.sha256(self.residual_path.read_bytes()).hexdigest(),
            }
            self.persist()
        if A.ANY and "ablation" not in self.state:   # the ablations' own record (ablation.py); never in a plain run
            self.state["ablation"] = A.initial_state()
            self.persist()
        self.max_rounds = self.state["max_rounds"] + A.RESET_BUDGET
        self.oracle_references = load_bank(
            self.state["bank"], self.residual_path, self.root / "oracle", self.state["oracle_bank_sha256"]
        )

    def persist(self):
        path = self.root / "state.json"
        tmp = self.root / "state.tmp"
        tmp.write_text(json.dumps(self.state, allow_nan=False))
        tmp.chmod(0o600)
        tmp.replace(path)

    def audit(self, event):
        path = self.root / "audit.jsonl"
        try:
            if path.exists() and path.stat().st_size > 50 * 2**20:
                return   # an agent's request flood must not fill the sidecar's disk
            with path.open("a") as f:
                f.write(json.dumps({"time": time.time(), **event}, allow_nan=False) + "\n")
        except OSError:
            pass   # evidence for people, never part of the verdict

    def call(self, operation, arguments):
        try:
            if A.ANY and self.state["ablation"]["finished"] is not None:
                return {"error": "Session finished"}
            if self.state["sealed"] or time.time() > self.state["deadline"] or self.state["infrastructure_error"]:
                if A.STATE_QUERY and operation in ("state_entities", "state_query"):
                    return {"error": "Session finished"}
                raise ValueError("Session closed")
            if A.ANY and operation in ("finish", "state_entities", "state_query", "save_state", "load_state"):
                return self.ablation_call(operation, arguments)
            if operation == "describe" and arguments == {}:
                result = {
                    "schema": "landing-adaptation/2",
                    "task_version": TASK_VERSION,
                    "rendering": {
                        "style": STYLE,
                        "width": WIDTH,
                        "height": HEIGHT,
                        "video_fps": FPS,
                        "camera": "fixed world camera",
                    },
                    "randomization": {
                        "initial_xy_m": INITIAL_XY_RANGE,
                        "initial_body_height_m": INITIAL_HEIGHT_RANGE,
                        "pad_xy_m": PAD_XY_RANGE,
                        "min_horizontal_travel_m": MIN_TRAVEL,
                    },
                    "goal": "Fly from the randomized start to the independently placed, fixed pad; land gently and settle.",
                    "action": "Validated numeric landing-policy/2, four rotor thrusts executed by a fixed controller.",
                    "feedback": "Known commanded pad position, 20 Hz noisy navigation, IMU specific force, rotor RPM and own commands; 1 Hz camera frames.",
                    "control_dt_s": DT,
                    "duration_s": HORIZON,
                    "scoring": {
                        "version": SCORE_VERSION,
                        "success_points": SUCCESS_POINTS,
                        "time_bonus_points": TIME_BONUS_POINTS,
                        "settle_duration_s": SETTLE_TIME,
                        "oracle_time_relaxation": ORACLE_TIME_RELAXATION,
                        "formula": "60 + 40 * clip((16 - completion_time_s) / (16 - 1.10 * private_oracle_time_s), 0, 1) if safe success, else 0",
                        "reference": "Per-case full-model numerical oracle search with exact state and residual, bounded controller family and identical safety limits; frozen before adaptation. Best verified feasible time, not a certified global optimum.",
                        "completion": "Start-to-landing time including one continuous settled second; instability resets completion. Must remain settled through episode end.",
                        "safety": "On-pad feet contact only, first-contact vertical speed <0.4 m/s and horizontal speed <0.25 m/s; settled XY error <0.15 m, tilt <0.15 rad, speed <0.08 m/s; no crash or arena exit.",
                        "aggregation": "Mean episode score; separately report success rate and mean successful completion time. Compare policies on the same private case bank.",
                    },
                    "default_policy": DEFAULT,
                    "rounds_remaining": self.state["max_rounds"] - len(self.state["rounds"]),
                    "adaptation_cases": len(self.state["bank"]["adaptation"]),
                    "final_cases": len(self.state["bank"]["held_out"]),
                    "deadline_unix": self.state["deadline"],
                    "training": "Editable nominal simulator and residual estimator.",
                    "hidden": "Deployment dynamics, seeds, actual state, contact records, oracle policies/timings/trajectories and scores are not returned.",
                }
                if A.ANY:
                    result["rounds_remaining"] = self.max_rounds - len(self.state["rounds"])
                    if A.STATE_OPS:
                        result.update(max_rounds=self.max_rounds, state_ops=A.OPS_NOTE.format(rounds=self.max_rounds))
                    if A.STATE_QUERY:
                        result["state_query"] = A.QUERY_NOTE
                    if A.HIDE_SUCCESS:
                        result.update(success_signal="hidden", finish=A.FINISH_NOTE)
            elif operation == "deploy" and isinstance(arguments, dict) and set(arguments) == {"policy", "diagnosis"}:
                policy = validate(arguments["policy"])
                note = arguments["diagnosis"]
                if not isinstance(note, str) or len(note) > 2000:
                    raise ValueError("Invalid diagnosis")
                if len(self.state["rounds"]) >= self.max_rounds:
                    raise ValueError("Budget exhausted")
                ident = f"round-{len(self.state['rounds']) + 1}"
                folder = self.root / ident
                folder.mkdir()
                (folder / "policy.json").write_text(json.dumps(policy, sort_keys=True))
                entry = {"id": ident, "status": "running", "policy_sha256": digest(policy), "diagnosis": note}
                bank = list(enumerate(self.state["bank"]["adaptation"]))
                start = None
                if A.ANY:
                    ab = self.state["ablation"]
                    start, ab["pending"] = ab["pending"], None   # a load arms one deployment
                    if start is not None:
                        bank = [bank[start["case"]]]
                        entry["start"] = {k: start[k] for k in ("handle", "case", "t")}
                    entry["started_at"] = time.time()
                    entry["schedule"] = (start["schedule"] if start else []) + [[start["t"] if start else 0.0, ident]]
                self.state["rounds"].append(entry)
                self.persist()  # Charge before simulation, including failed jobs.
                cases = []
                try:
                    for i, case in bank:
                        if self.stopping:   # the agent's time is up: no simulation for this round after the cutoff
                            entry["status"] = "aborted_at_cutoff"
                            self.persist()
                            raise ValueError("Session closed")
                        path = folder / f"case-{i}"
                        feedback, _ = rollout(
                            policy if not (A.STATE_QUERY or A.STATE_OPS) else self._policy(entry["schedule"][0][1]),
                            residual_path=self.residual_path,
                            out=path,
                            render=self.render,
                            reference_time_s=self.oracle_references["adaptation"][i]["oracle_time_s"],
                            **case,
                            **({"ablation": self.ablation_hook(entry)} if A.STATE_QUERY or A.STATE_OPS else {}),
                        )
                        if A.STATE_QUERY or A.STATE_OPS:
                            self.ablation_after(entry, path)
                        cases.append({"case": i, **public_feedback(feedback, path)})
                except ValueError:
                    if entry["status"] == "aborted_at_cutoff":
                        raise
                    entry["status"] = "failed"
                    raise RuntimeError("Deployment failed")
                except Exception as error:
                    # the evaluator failed on a validated policy (divergence is a crash, not an error): the trial is
                    # void, an infrastructure failure; the round never stays "running"
                    entry["status"] = "failed"
                    raise RuntimeError("Deployment failed") from error
                entry["status"] = "completed"
                entry["completed_at"] = time.time()
                self.persist()
                result = {
                    "round_id": ident,
                    "policy_sha256": digest(policy),
                    "deployments": cases,
                    "rounds_remaining": self.max_rounds - len(self.state["rounds"]),
                }
                if A.ANY and start is not None:
                    result.update(start=entry["start"], load_verified=entry["load_verified"])
                (folder / "agent-feedback.json").write_text(json.dumps(result, allow_nan=False))
            elif operation == "seal" and isinstance(arguments, dict) and set(arguments) == {"round_id", "summary"}:
                if not isinstance(arguments["summary"], str) or len(arguments["summary"]) > 2000:
                    raise ValueError("Invalid summary")
                choices = [
                    r for r in self.state["rounds"] if r["status"] == "completed" and r["id"] == arguments["round_id"]
                ]
                if not choices:
                    raise ValueError("Select a completed round")
                self.state.update(sealed=True, selected=choices[0]["id"], summary=arguments["summary"])
                if A.HIDE_SUCCESS:   # a seal ends adaptation as /finish does
                    self.state["ablation"].update(finished=time.time(), ended_by="seal")
                self.persist()
                result = {"sealed": True, "round_id": choices[0]["id"], "policy_sha256": choices[0]["policy_sha256"]}
            else:
                raise ValueError("Unsupported operation")
            self.audit(
                {
                    "operation": operation,
                    "arguments": arguments,
                    "outcome": "accepted",
                    "response_sha256": digest(result),
                }
            )
            return result
        except (ValueError, TypeError, KeyError):
            self.audit({"operation": str(operation)[:80], "outcome": "rejected"})
            return {"error": "Request rejected"}
        except Exception:
            self.state["infrastructure_error"] = True
            self.persist()
            self.audit({"operation": str(operation)[:80], "outcome": "infrastructure_error"})
            raise

    # ------------------------------------------------------------ the ablations (ablation.py; only with a switch on)

    def _policy(self, ident):
        return validate(json.loads((self.root / ident / "policy.json").read_text()))

    def ablation_hook(self, entry):
        later = [[t, str((self.root / ident / "policy.json").resolve())] for t, ident in entry["schedule"][1:]]
        self._hook = A.Hook(later, A.STATE_QUERY)
        return self._hook

    def ablation_after(self, entry, path):
        """After one development episode: its trace (state queries, save / load) and a load's digest check."""
        self._hook.write(str(path))
        start = entry.get("start")
        if start is not None:
            trace = json.loads((path / A.TRACE).read_text())
            hit = [d for t, d in zip(trace["t"], trace["digest"]) if abs(t - start["t"]) < 1e-6]
            ab = self.state["ablation"]
            handle = next(h for h in ab["handles"] + [ab.get("_loaded") or {}] if h.get("handle") == start["handle"])
            entry["load_verified"] = bool(hit) and hit[0] == handle["digest"]
            if not entry["load_verified"]:
                self.audit({"operation": "load_state", "round": entry["id"], "outcome": "state_digest_mismatch"})

    def _trace(self, ident, case):
        return json.loads((self.root / ident / f"case-{case}" / A.TRACE).read_text())

    def _completed(self):
        n = len(self.state["bank"]["adaptation"])
        return {r["id"]: ([r["start"]["case"]] if r.get("start") else list(range(n)))
                for r in self.state["rounds"] if r["status"] == "completed"}

    def ablation_call(self, op, args):
        import math

        s = self.state
        ab = s["ablation"]
        if not isinstance(args, dict):
            raise ValueError("Request object")
        if op == "finish" and A.HIDE_SUCCESS:
            if set(args) - {"round_id", "summary"}:
                raise ValueError("Finish fields")
            summary = args.get("summary", "")
            if not isinstance(summary, str) or len(summary) > 2000:
                raise ValueError("Summary")
            eligible = [r for r in s["rounds"] if r["status"] == "completed"
                        and r.get("completed_at", float("inf")) <= s["deadline"]]
            if "round_id" in args:
                ident = args["round_id"]
                if ident not in [r["id"] for r in eligible]:
                    raise ValueError("Select a completed round")
            else:
                ident = eligible[-1]["id"] if eligible else None
            s.update(sealed=True, selected=ident, summary=summary)
            ab.update(finished=time.time(), ended_by="finish")
            self.persist()
            self.audit({"operation": "finish", "round": ident, "outcome": "accepted"})
            return {"ok": True, "done": True, "reason": "finished", "round_id": ident}
        if op == "state_entities" and A.STATE_QUERY and args == {}:
            return {**A.entities({}), "rounds": list(self._completed())}
        if op == "state_query" and A.STATE_QUERY:
            table = A.entities({})
            p, error = A.plan(table, args, self._completed())
            if error is not None:
                return error
            result = A.answer(table, p, {c: self._trace(p["round_id"], c) for c in p["cases"]})
            ab["state_queries"] += 1
            self.persist()
            self.audit({"operation": "state_query", "round": p["round_id"], "cases": p["cases"],
                        "names": sorted(p["names"]), "t": p["t"], "outcome": "accepted"})
            return {**result, "state_queries": ab["state_queries"]}
        if op == "save_state" and A.STATE_OPS:
            rounds = self._completed()
            if set(args) != {"round_id", "case", "t"}:
                return {"error": "save_state takes round_id, case and t", "rounds": list(rounds)}
            ident, case, t = args["round_id"], args["case"], args["t"]
            if type(ident) is not str or ident not in rounds:
                return {"error": "unknown round_id (a completed round)", "rounds": list(rounds)}
            if type(case) is not int or case not in rounds[ident]:
                return {"error": "unknown case", "cases": rounds[ident]}
            if type(t) not in (int, float) or not math.isfinite(t):
                return {"error": "t is a time in seconds"}
            trace = self._trace(ident, case)
            at = [k for k, x in enumerate(trace["t"]) if x <= t + 1e-9]
            if not at:
                return {"error": "no telemetry sample at or before t", "first_t": trace["t"][0] if trace["t"] else None}
            k = at[-1]
            point = trace["t"][k]
            row = next(r for r in s["rounds"] if r["id"] == ident)
            name = f"s{ab['next_handle']}"
            entry = {"handle": name, "round_id": ident, "case": case, "t": point, "digest": trace["digest"][k],
                     "schedule": [seg for seg in row["schedule"] if seg[0] < point - 1e-9]}
            ab["next_handle"] += 1
            ab["saves"] += 1
            ab["handles"] = (ab["handles"] + [entry])[-A.MAX_HANDLES:]
            self.persist()
            self.audit({"operation": "save_state", "handle": name, "round": ident, "case": case, "t": point,
                        "outcome": "accepted"})
            return {"handle": name, "round_id": ident, "case": case, "t": point, "saves": ab["saves"]}
        if op == "load_state" and A.STATE_OPS:
            if set(args) != {"handle"}:
                return {"error": "load_state takes handle (null cancels)", "handles": [h["handle"] for h in ab["handles"]]}
            if args["handle"] is None:
                ab["pending"] = None
                self.persist()
                return {"loaded": None, "next_deployment": "every development case from its start"}
            entry = next((h for h in ab["handles"] if h["handle"] == args["handle"]), None)
            if entry is None:
                return {"error": "unknown handle", "handles": [h["handle"] for h in ab["handles"]]}
            ab["handles"] = [h for h in ab["handles"] if h is not entry] + [entry]
            ab["pending"] = entry
            ab["_loaded"] = entry
            ab["loads"] += 1
            self.persist()
            self.audit({"operation": "load_state", "handle": entry["handle"], "outcome": "accepted"})
            return {"loaded": entry["handle"], "case": entry["case"], "t": entry["t"], "loads": ab["loads"],
                    "next_deployment": f"case {entry['case']} from t = {entry['t']} s, the deployed policy from there"}
        raise ValueError("Unsupported operation")

    def ablation_fields(self, final, selected):
        """final.json's ablation fields (diagnostics and counts; the verdict never reads them)."""
        s = self.state
        ab = s["ablation"]
        t0 = (s.get("native_started_at") or time.time())
        out = {}
        if A.HIDE_SUCCESS:
            ok = []
            for r in s["rounds"]:
                if r["status"] != "completed":
                    continue
                try:
                    if all(json.loads((self.root / r["id"] / f"case-{c}" / "record.json").read_text())
                           ["metrics"]["success"] for c in self._completed()[r["id"]]):
                        ok.append(r["id"])
                except (OSError, ValueError, KeyError):
                    pass
            out.update(
                success_signal="hidden",
                ended_by="finish" if ab["ended_by"] in ("finish", "seal") else "timeout",
                finish_time_s=None if ab["finished"] is None else round(ab["finished"] - t0, 3),
                hidden_success_seen=None if selected is None else selected["id"] in ok,
                trial_hidden_success_seen=bool(ok),
            )
        if A.STATE_QUERY:
            out["state_queries"] = ab["state_queries"]
        if A.STATE_OPS:
            rounds = s["rounds"]
            n = len(rounds)
            out.update(
                rounds=n, round_budget=self.max_rounds, reset_budget=A.RESET_BUDGET,
                resets=max(0, n - A.STANDARD_ROUNDS), saves=ab["saves"], loads=ab["loads"], development_episodes=n,
                development_episodes_log=[{"episode": r["id"], "began": "load" if r.get("start") else "start",
                                           "cases": self._completed().get(r["id"], [r["start"]["case"]] if r.get("start") else
                                                                       list(range(len(s["bank"]["adaptation"])))),
                                           **({"from": r["start"]} if r.get("start") else {}),
                                           "t_start_s": round(r["started_at"] - t0, 3) if r.get("started_at") else None,
                                           "t_end_s": round(r["completed_at"] - t0, 3) if r.get("completed_at") else None,
                                           "ended": r["status"]} for r in rounds],
                load_mismatches=[r["id"] for r in rounds if r.get("load_verified") is False],
            )
            first = False
            if selected is not None:
                index = [r["id"] for r in rounds].index(selected["id"])
                loaded = sum(1 for r in rounds[: index + 1] if r.get("start"))
                first = final["success"] and index < A.STANDARD_ROUNDS and loaded == 0
                if final["success"]:
                    out.update(resets_at_success=max(0, index + 1 - A.STANDARD_ROUNDS), loads_at_success=loaded)
            out["first_success"] = int(bool(first))
        return out
