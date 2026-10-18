"""Persistent bounded adaptation, strict feedback projection, and fresh-process held-out replay."""

import hashlib, json, os, shutil, subprocess, sys, time, uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .adapter import validate, feedback
from .runtime_limits import runtime_limits


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def atomic(path, value):
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")   # unique: the signal handler and a thread may both write
    tmp.write_text(json.dumps(value, sort_keys=True, allow_nan=False))
    tmp.replace(path)


AUDIT_CAP_BYTES = 50 * 2**20   # an agent's request flood must not fill the sidecar's disk (that would void the trial)
HELD_OUT_WORKERS = 4           # the sim service's CPU cap: one single-threaded worker process per CPU


class Session:
    def __init__(self, root, instance, wall_clock_s=3600, render=True):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.instance = instance
        self.render = render
        self.wall = wall_clock_s
        self.family = instance["family"]
        self.limits = runtime_limits(instance)
        self.sha = digest(instance)
        self.path = self.root / "state.json"
        self.proc = None   # the running episode worker (killed when the agent's time is up: its round cannot count)
        self.stopping = False   # set (signal-safe) when the agent's time is up: no further episode starts for a round
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

    def close(self, cutoff=None):
        """Persist an operator cutoff separately from adaptation's mutable state."""
        path = self.root / "cutoff.json"
        if path.exists():
            return json.loads(path.read_text())["cutoff"]
        cutoff = time.time() if cutoff is None else cutoff
        atomic(path, {"cutoff": cutoff})
        return cutoff

    def persist(self):
        atomic(self.path, self.state)

    def audit(self, event):
        path = self.root / "audit.jsonl"
        try:
            # past the cap only rejected requests are dropped: deployments, seals and finalization are always recorded
            rejected = event.get("status") == "rejected" or event.get("outcome") == "rejected"
            if rejected and path.exists() and path.stat().st_size > AUDIT_CAP_BYTES:
                return
            with path.open("a") as f:
                f.write(json.dumps({"time": time.time(), **event}, allow_nan=False) + "\n")
        except OSError:
            pass   # the audit log is evidence for people, never part of the verdict

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
        if (self.root / "cutoff.json").exists() or s["sealed"] or s["infra_error"] or time.time() > s["deadline"]:
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
            folder.mkdir(exist_ok=True)   # a crash before the round was persisted left it behind
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
                    if self.stopping:   # the agent's time is up: no simulation for this round after the cutoff
                        raise RuntimeError("cutoff")
                    target = folder / f"case-{j}"
                    record = self.episode(policy, case, target, self.render)
                    observations.append(feedback(self.family, record, target, sampling=self.limits))
                result = {
                    "round_id": i,
                    "policy_sha256": row["policy_sha256"],
                    "feedback": observations,
                    "remaining_rounds": 3 - len(s["rounds"]),
                }
                atomic(folder / "agent-view.json", result)   # before the round counts as completed (`result` reads it)
                row.update(status="completed", completed_at=time.time())
                self.persist()
                self.audit({"operation": "feedback", "round": i, "sha256": digest(result)})
                return result
            except Exception:
                if self.stopping or (self.root / "cutoff.json").exists():
                    # the agent's time ran out during this round: the worker was stopped, the round is not graded
                    row["status"] = "aborted_at_cutoff"
                    self.persist()
                    return {"error": "Session closed"}
                # the evaluator failed (a policy cannot make it fail: divergence is a failed episode, validated
                # inputs only): the trial is void, an infrastructure failure (PROTOCOL H.5), never the agent's 0
                s["infra_error"] = True
                row["status"] = "failed"
                self.persist()
                self.audit({"operation": "deploy", "round": i, "status": "infrastructure_error"})
                return {"error": "Evaluator failure: this trial is void (infrastructure), not a result"}
        if op == "result" and set(args) == {"round_id"}:
            # the stored response of a completed round (a client that lost the deploy response); runs no simulation
            i = args["round_id"]
            if type(i) is not int or not 0 <= i < len(s["rounds"]) or s["rounds"][i]["status"] != "completed":
                raise ValueError("Round")
            return json.loads((self.root / f"round-{i}" / "agent-view.json").read_text())
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

    def episode(self, policy, case, out, render, track=True):
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
        timeout = self.limits["worker_seconds"] if render else self.limits["replay_seconds"]
        with out.with_suffix(".worker.log").open("w") as log:
            proc = subprocess.Popen(
                [sys.executable, "-m", "scripts.control_transfer.trusted.adapter", "--request", str(request_path)],
                stdout=log,
                stderr=log,
                env={
                    **os.environ,
                    "MUJOCO_GL": "osmesa",
                    "OPENBLAS_NUM_THREADS": "1",
                    "CUDA_VISIBLE_DEVICES": "",
                    "NVIDIA_VISIBLE_DEVICES": "void",
                    "LIBGL_ALWAYS_SOFTWARE": "1",
                },
            )
            if track:
                self.proc = proc
                if self.stopping:   # the cutoff came while this worker was starting
                    proc.kill()
            try:
                code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                raise
            finally:
                if track:
                    self.proc = None
            if code != 0:
                raise subprocess.CalledProcessError(code, "episode worker")
        return json.loads((out / "record.json").read_text())

    def stop_worker(self):
        """Signal-safe: kill a deployment's running episode worker (the agent's time is up; that round is not graded)."""
        self.stopping = True   # first: a worker starting after this reads it and is killed by episode() itself
        proc = self.proc
        if proc is not None:
            try:
                proc.kill()
            except OSError:
                pass

    def finalize(self, cutoff=None):
        final_path = self.root / "final.json"
        if final_path.exists():
            return json.loads(final_path.read_text())
        s = self.state
        cutoff = min(self.close(cutoff), s["deadline"] or time.time())
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
            "success": False,
            "episodes": [],
        }
        try:
            if selected and not s["infra_error"]:
                policy = self.root / f"round-{selected['id']}" / "policy"
                if hashlib.sha256(policy.read_bytes()).hexdigest() != selected["policy_sha256"]:
                    raise ValueError("Changed policy")
                final["policy_sha256"] = selected["policy_sha256"]
                held = self.root / "held-out"
                if held.exists():
                    # Preserve interrupted evidence and replay the frozen policy/bank.
                    # The persisted cutoff prevents new submissions during recovery.
                    archived = self.root / ("held-out-interrupted-" + uuid.uuid4().hex)
                    held.rename(archived)
                    self.audit({"operation": "finalize_restart", "archived": archived.name})
                held.mkdir()
                cases = list(enumerate(self.instance["bank"]["held_out"]))

                def evaluate(item):
                    # two fresh processes, no rendering: the verdict never waits for or depends on a video (PROTOCOL §4)
                    i, case = item
                    a = self.episode(policy, case, held / f"case-{i}-a", False, track=False)
                    b = self.episode(policy, case, held / f"case-{i}-b", False, track=False)
                    # Compare physical state hash, numeric grade and every noisy observation.
                    keys = ("metrics", "feedback", "state_sha256")
                    if digest({k: a[k] for k in keys}) != digest({k: b[k] for k in keys}):
                        raise RuntimeError("Fresh replay mismatch")
                    m = a["metrics"]
                    return {
                        "case": i,
                        "success": bool(m["success"]),
                        "score": float(m["score"]),
                        "replay_verified": True,
                        "state_sha256": a["state_sha256"],
                    }

                pool = ThreadPoolExecutor(HELD_OUT_WORKERS)
                try:
                    final["episodes"] = list(pool.map(evaluate, cases))
                finally:
                    pool.shutdown(wait=True, cancel_futures=True)   # a failed case stops the cases not yet started
                final["success"] = all(r["success"] for r in final["episodes"])
        except Exception:
            final["infra_error"] = True
            self.audit({"operation": "finalize", "status": "infrastructure_error"})
        final["evidence_sha256"] = digest(final["episodes"])
        final["graded_by"] = "live"   # the sidecar's own evaluation of the selected policy; no replay of the agent's actions
        final["video_source"] = "render"   # replay.mp4: a rendered run after the verdict (video.json)
        atomic(final_path, final)
        return final

    def render_video(self, final):
        """After the verdict (PROTOCOL §4): one rendered run of the selected policy per held-out case, joined into
        /data/replay.mp4 (the held-out evaluation the verdict is about). Best effort: it never changes final.json."""
        status = {"video": None, "cases": [], "matches_graded": None}
        try:
            (self.root / "replay.mp4").unlink(missing_ok=True)   # a restart renders again from scratch
            if final.get("no_submission"):
                status["reason"] = "no_submission: no graded episode"
            if final.get("infra_error") or final.get("no_submission") or not final.get("episodes"):
                return
            selected = next(r for r in self.state["rounds"] if r["policy_sha256"] == final["policy_sha256"])
            policy = self.root / f"round-{selected['id']}" / "policy"
            video_dir = self.root / "held-out-video"
            if video_dir.exists():
                shutil.rmtree(video_dir)
            video_dir.mkdir()

            def render(item):
                i, case = item
                try:
                    record = self.episode(policy, case, video_dir / f"case-{i}", True, track=False)
                    return i, record["state_sha256"]
                except Exception:   # one case without a video does not cost the others theirs
                    return i, None

            cases = list(enumerate(self.instance["bank"]["held_out"]))
            with ThreadPoolExecutor(max(1, HELD_OUT_WORKERS // 2)) as pool:
                hashes = dict(pool.map(render, cases))
            status["matches_graded"] = all(hashes.get(r["case"]) == r["state_sha256"] for r in final["episodes"])
            parts = [video_dir / f"case-{i}" / "video.mp4" for i, _ in cases]
            parts = [p for p in parts if p.is_file()]
            status["cases"] = [p.parent.name for p in parts]
            if parts:
                listing = video_dir / "concat.txt"
                listing.write_text("".join(f"file '{p}'\n" for p in parts))
                tmp = self.root / "replay.tmp.mp4"   # never a truncated replay.mp4 (a collect budget running out)
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                                "-c", "copy", str(tmp)], check=True, timeout=300, capture_output=True)
                os.replace(tmp, self.root / "replay.mp4")
                status["video"] = "replay.mp4"
        except Exception as error:
            status["error"] = type(error).__name__
        finally:
            atomic(self.root / "video.json", {**status, "done": True})
