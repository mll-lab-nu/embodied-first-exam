"""Persistent bounded adaptation, strict feedback projection, and fresh-process held-out replay."""

import hashlib, json, os, subprocess, sys, time
from pathlib import Path
from .adapter import validate, feedback


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def atomic(path, value):
    path = Path(path)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, sort_keys=True, allow_nan=False))
    tmp.replace(path)


class Session:
    def __init__(self, root, instance, wall_clock_s=3600, render=True):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.instance = instance
        self.render = render
        self.wall = wall_clock_s
        self.family = instance["family"]
        self.sha = digest(instance)
        self.path = self.root / "state.json"
        bank = instance["bank"]
        ids = [(c["plant_seed"], c["episode_seed"]) for x in bank.values() for c in x]
        if set(bank) != {"adaptation", "held_out"} or not all(bank.values()) or len(ids) != len(set(ids)):
            raise ValueError("Invalid case bank")
        if instance.get("transfer_track") == "same-plant":
            if len({c["plant_seed"] for cases in bank.values() for c in cases}) != 1:
                raise ValueError("Same-plant adaptation requires persistent hidden dynamics")
        if self.path.exists():
            self.state = json.loads(self.path.read_text())
            if self.state["instance_sha256"] != self.sha:
                raise ValueError("Frozen instance changed")
            if any(r["status"] == "running" for r in self.state["rounds"]):
                self.state["infra_error"] = True
        else:
            self.state = {
                "instance_sha256": self.sha,
                "rounds": [],
                "sealed": False,
                "selected": None,
                "deadline": None,
                "infra_error": False,
            }
        self.persist()

    def persist(self):
        atomic(self.path, self.state)

    def audit(self, event):
        with (self.root / "audit.jsonl").open("a") as f:
            f.write(json.dumps({"time": time.time(), **event}, allow_nan=False) + "\n")

    def call(self, operation, args):
        try:
            return self._call(operation, args)
        except (ValueError, TypeError, KeyError):
            self.audit({"operation": str(operation)[:64], "status": "rejected"})
            return {"error": "Request rejected"}

    def _call(self, op, args):
        if not isinstance(args, dict):
            raise ValueError("Request object")
        s = self.state
        if s["deadline"] is None:
            s["deadline"] = time.time() + self.wall
            self.persist()
        if s["sealed"] or s["infra_error"] or time.time() > s["deadline"]:
            raise ValueError("Closed")
        if op == "describe" and args == {}:
            return {
                **self.instance["public"],
                "remaining_rounds": 3 - len(s["rounds"]),
                "time_left_s": max(0, s["deadline"] - time.time()),
            }
        if op == "deploy" and set(args) == {"policy", "diagnosis"}:
            if len(s["rounds"]) >= 3 or not isinstance(args["diagnosis"], str) or len(args["diagnosis"]) > 2000:
                raise ValueError("Deployment budget")
            raw = validate(self.family, args["policy"])
            i = len(s["rounds"])
            folder = self.root / f"round-{i}"
            folder.mkdir()
            policy = folder / "policy"
            policy.write_bytes(raw)
            row = {
                "id": i,
                "status": "running",
                "policy_sha256": hashlib.sha256(raw).hexdigest(),
                "diagnosis": args["diagnosis"],
                "started_at": time.time(),
            }
            s["rounds"].append(row)
            self.persist()
            self.audit(
                {
                    "operation": "deploy",
                    "round": i,
                    "policy_sha256": row["policy_sha256"],
                    "diagnosis": args["diagnosis"],
                }
            )
            try:
                observations = []
                for j, case in enumerate(self.instance["bank"]["adaptation"]):
                    target = folder / f"case-{j}"
                    record = self.episode(policy, case, target, self.render)
                    observations.append(feedback(self.family, record, target))
                row.update(status="completed", completed_at=time.time())
                self.persist()
                result = {
                    "round_id": i,
                    "policy_sha256": row["policy_sha256"],
                    "feedback": observations,
                    "remaining_rounds": 3 - len(s["rounds"]),
                }
                atomic(folder / "agent-view.json", result)
                self.audit({"operation": "feedback", "round": i, "sha256": digest(result)})
                return result
            except Exception:
                s["infra_error"] = True
                row["status"] = "failed"
                self.persist()
                raise
        if op == "seal" and set(args) == {"round_id", "summary"}:
            i = args["round_id"]
            if (
                type(i) is not int
                or not 0 <= i < len(s["rounds"])
                or not isinstance(args["summary"], str)
                or len(args["summary"]) > 2000
            ):
                raise ValueError("Selection")
            row = s["rounds"][i]
            if row["status"] != "completed" or row["completed_at"] > s["deadline"]:
                raise ValueError("Ineligible")
            s.update(sealed=True, selected=i, summary=args["summary"])
            self.persist()
            self.audit({"operation": "seal", "round": i, "summary": args["summary"]})
            return {"sealed": True, "round_id": i}
        raise ValueError("Unknown operation")

    def episode(self, policy, case, out, render):
        request = {
            "family": self.family,
            "policy": str(policy.resolve()),
            "case": case,
            "out": str(out.resolve()),
            "render": render,
            "asset": self.instance.get("private_asset"),
        }
        request_path = out.with_suffix(".request.json")
        atomic(request_path, request)
        with out.with_suffix(".worker.log").open("w") as log:
            subprocess.run(
                [sys.executable, "-m", "scripts.control_transfer.trusted.adapter", "--request", str(request_path)],
                stdout=log,
                stderr=log,
                check=True,
                timeout=600,
                env={
                    **os.environ,
                    "MUJOCO_GL": "osmesa",
                    "OPENBLAS_NUM_THREADS": "1",
                    "CUDA_VISIBLE_DEVICES": "",
                    "NVIDIA_VISIBLE_DEVICES": "void",
                    "LIBGL_ALWAYS_SOFTWARE": "1",
                },
            )
        return json.loads((out / "record.json").read_text())

    def finalize(self, cutoff=None):
        final_path = self.root / "final.json"
        if final_path.exists():
            return json.loads(final_path.read_text())
        s = self.state
        cutoff = min(cutoff or time.time(), s["deadline"] or time.time())
        rows = [r for r in s["rounds"] if r["status"] == "completed" and r["completed_at"] <= cutoff]
        selected = (
            next((r for r in rows if r["id"] == s["selected"]), None) if s["sealed"] else (rows[-1] if rows else None)
        )
        final = {
            "schema": "control-transfer-final/1",
            "instance_sha256": self.sha,
            "finalized": True,
            "infra_error": s["infra_error"],
            "no_submission": selected is None,
            "episodes": [],
        }
        try:
            if selected and not s["infra_error"]:
                policy = self.root / f"round-{selected['id']}" / "policy"
                if hashlib.sha256(policy.read_bytes()).hexdigest() != selected["policy_sha256"]:
                    raise ValueError("Changed policy")
                final["policy_sha256"] = selected["policy_sha256"]
                held = self.root / "held-out"
                held.mkdir()
                for i, case in enumerate(self.instance["bank"]["held_out"]):
                    a = self.episode(policy, case, held / f"case-{i}-a", self.render)
                    b = self.episode(policy, case, held / f"case-{i}-b", False)
                    # Compare physical state hash, numeric grade and every noisy observation; encoded video is not physics.
                    keys = ("metrics", "feedback", "state_sha256")
                    replayed = digest({k: a[k] for k in keys}) == digest({k: b[k] for k in keys})
                    if not replayed:
                        raise RuntimeError("Fresh replay mismatch")
                    m = a["metrics"]
                    final["episodes"].append(
                        {
                            "case": i,
                            "success": bool(m["success"]),
                            "score": float(m["score"]),
                            "replay_verified": True,
                            "state_sha256": a["state_sha256"],
                        }
                    )
        except Exception:
            final["infra_error"] = True
            self.audit({"operation": "finalize", "status": "infrastructure_error"})
        final["evidence_sha256"] = digest(final["episodes"])
        atomic(final_path, final)
        return final
