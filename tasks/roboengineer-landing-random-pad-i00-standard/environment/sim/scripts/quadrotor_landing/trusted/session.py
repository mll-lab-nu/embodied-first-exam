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
            if self.state["sealed"] or time.time() > self.state["deadline"] or self.state["infrastructure_error"]:
                raise ValueError("Session closed")
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
            elif operation == "deploy" and isinstance(arguments, dict) and set(arguments) == {"policy", "diagnosis"}:
                policy = validate(arguments["policy"])
                note = arguments["diagnosis"]
                if not isinstance(note, str) or len(note) > 2000:
                    raise ValueError("Invalid diagnosis")
                if len(self.state["rounds"]) >= self.state["max_rounds"]:
                    raise ValueError("Budget exhausted")
                ident = f"round-{len(self.state['rounds']) + 1}"
                folder = self.root / ident
                folder.mkdir()
                (folder / "policy.json").write_text(json.dumps(policy, sort_keys=True))
                entry = {"id": ident, "status": "running", "policy_sha256": digest(policy), "diagnosis": note}
                self.state["rounds"].append(entry)
                self.persist()  # Charge before simulation, including failed jobs.
                cases = []
                try:
                    for i, case in enumerate(self.state["bank"]["adaptation"]):
                        if self.stopping:   # the agent's time is up: no simulation for this round after the cutoff
                            entry["status"] = "aborted_at_cutoff"
                            self.persist()
                            raise ValueError("Session closed")
                        path = folder / f"case-{i}"
                        feedback, _ = rollout(
                            policy,
                            residual_path=self.residual_path,
                            out=path,
                            render=self.render,
                            reference_time_s=self.oracle_references["adaptation"][i]["oracle_time_s"],
                            **case,
                        )
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
                    "rounds_remaining": self.state["max_rounds"] - len(self.state["rounds"]),
                }
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
