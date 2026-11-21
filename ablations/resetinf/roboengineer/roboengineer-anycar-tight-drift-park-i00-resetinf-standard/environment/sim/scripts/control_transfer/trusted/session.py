"""Persistent bounded adaptation, strict feedback projection, and fresh-process held-out replay."""

import hashlib, json, math, os, shutil, subprocess, sys, time, uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .adapter import validate, feedback
from .runtime_limits import runtime_limits
from . import ablation as A


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
        if A.ANY:   # the ablations' own record (ablation.py); a plain session's state.json never has it
            self.state.setdefault("ablation", A.initial_state())
        self.max_rounds = A.STANDARD_ROUNDS + A.RESET_BUDGET
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
        if A.ANY and s["ablation"]["finished"] is not None:
            return {"error": "Session finished"}
        if (self.root / "cutoff.json").exists() or s["sealed"] or s["infra_error"] or time.time() > s["deadline"]:
            if A.STATE_QUERY and op in ("state_entities", "state_query"):
                return {"error": "Session finished"}
            raise ValueError("Closed")
        if op == "describe" and args == {}:
            if A.ANY:
                return self.ablation_describe()
            return {
                **self.instance["public"],
                "remaining_rounds": 3 - len(s["rounds"]),
                "time_left_s": max(0, s["deadline"] - time.time()),
            }
        if A.ANY and op in ("finish", "state_entities", "state_query", "save_state", "load_state"):
            return self.ablation_call(op, args)
        if op == "deploy" and set(args) == {"policy", "diagnosis"}:
            if len(s["rounds"]) >= self.max_rounds or not isinstance(args["diagnosis"], str) or len(args["diagnosis"]) > 2000:
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
            cases = list(enumerate(self.instance["bank"]["adaptation"]))
            start = None
            if A.ANY:
                start, s["ablation"]["pending"] = s["ablation"]["pending"], None   # a load arms one deployment
                if start is not None:
                    cases = [cases[start["case"]]]
                    row["start"] = {k: start[k] for k in ("handle", "case", "t")}
                row["schedule"] = (start["schedule"] if start else []) + [[start["t"] if start else 0.0, i]]
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
                for j, case in cases:
                    if self.stopping:   # the agent's time is up: no simulation for this round after the cutoff
                        raise RuntimeError("cutoff")
                    target = folder / f"case-{j}"
                    if A.ANY:
                        record = self.ablation_episode(row, case, target)
                    else:
                        record = self.episode(policy, case, target, self.render)
                    observations.append(feedback(self.family, record, target, sampling=self.limits))
                result = {
                    "round_id": i,
                    "policy_sha256": row["policy_sha256"],
                    "feedback": observations,
                    "remaining_rounds": self.max_rounds - len(s["rounds"]),
                }
                if A.ANY and start is not None:
                    result.update(cases=[start["case"]], start=row["start"], load_verified=row["load_verified"])
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
            if A.HIDE_SUCCESS:   # a seal ends adaptation as /finish does
                s["ablation"].update(finished=time.time(), ended_by="seal")
            self.persist()
            self.audit({"operation": "seal", "round": i, "summary": args["summary"]})
            return {"sealed": True, "round_id": i}
        raise ValueError("Unknown operation")

    def episode(self, policy, case, out, render, track=True, ablation=None):
        request = {
            "family": self.family,
            "policy": str(policy.resolve()),
            "case": case,
            "out": str(out.resolve()),
            "render": render,
            "asset": self.instance.get("private_asset"),
            **({"ablation": ablation} if ablation is not None else {}),
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
        if A.ANY:
            final.update(self.ablation_fields(final, selected))
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

    # ------------------------------------------------------------ the ablations (ablation.py; only with a switch on)

    def ablation_describe(self):
        s = self.state
        out = {
            **self.instance["public"],
            "remaining_rounds": self.max_rounds - len(s["rounds"]),
            "time_left_s": max(0, s["deadline"] - time.time()),
        }
        if A.STATE_OPS:
            out.update(max_rounds=self.max_rounds, state_ops=A.OPS_NOTE.format(rounds=self.max_rounds))
        if A.STATE_QUERY:
            out["state_query"] = A.QUERY_NOTE
        if A.HIDE_SUCCESS:
            out.update(success_signal="hidden", finish=A.FINISH_NOTE)
        return out

    def _policy(self, round_id):
        return self.root / f"round-{round_id}" / "policy"

    def _trace(self, round_id, case):
        return json.loads((self.root / f"round-{round_id}" / f"case-{case}" / A.TRACE).read_text())

    def ablation_episode(self, row, case, target):
        """One development episode of a round: its policy schedule (a load: the saved path, then this round's policy),
        recording the true state (state queries) and the state digests (save / load)."""
        if not (A.STATE_QUERY or A.STATE_OPS):
            return self.episode(self._policy(row["id"]), case, target, self.render)
        schedule = row["schedule"]
        later = [[t, str(self._policy(rid).resolve())] for t, rid in schedule[1:]]
        record = self.episode(self._policy(schedule[0][1]), case, target, self.render,
                              ablation={"schedule": later, "store_states": A.STATE_QUERY})
        start = row.get("start")
        if start is not None:
            trace = json.loads((target / A.TRACE).read_text())
            hit = [d for t, d in zip(trace["t"], trace["digest"]) if abs(t - start["t"]) < 1e-6]
            handle = next(h for h in self.state["ablation"]["handles"] + [self.state["ablation"].get("_loaded") or {}]
                          if h.get("handle") == start["handle"])
            row["load_verified"] = bool(hit) and hit[0] == handle["digest"]
            if not row["load_verified"]:
                self.audit({"operation": "load_state", "round": row["id"], "status": "state_digest_mismatch"})
        return record

    def _completed(self):
        """{round id: [its case indices]} of the completed rounds."""
        n = len(self.instance["bank"]["adaptation"])
        return {r["id"]: ([r["start"]["case"]] if r.get("start") else list(range(n)))
                for r in self.state["rounds"] if r["status"] == "completed"}

    def ablation_call(self, op, args):
        s = self.state
        ab = s["ablation"]
        if op == "finish" and A.HIDE_SUCCESS:
            if set(args) - {"round_id", "summary"}:
                raise ValueError("Finish fields")
            summary = args.get("summary", "")
            if not isinstance(summary, str) or len(summary) > 2000:
                raise ValueError("Summary")
            eligible = [r for r in s["rounds"] if r["status"] == "completed" and r["completed_at"] <= s["deadline"]]
            if "round_id" in args:
                i = args["round_id"]
                if type(i) is not int or i not in [r["id"] for r in eligible]:
                    raise ValueError("Selection")
            else:
                i = eligible[-1]["id"] if eligible else None
            s.update(sealed=True, selected=i, summary=summary)
            ab.update(finished=time.time(), ended_by="finish")
            self.persist()
            self.audit({"operation": "finish", "round": i, "summary": summary})
            return {"ok": True, "done": True, "reason": "finished", "round_id": i}
        if op == "state_entities" and A.STATE_QUERY and args == {}:
            return {**A.entities(self.instance), "rounds": list(self._completed())}
        if op == "state_query" and A.STATE_QUERY:
            table = A.entities(self.instance)
            rounds = self._completed()
            p, error = A.plan(table, args, rounds)
            if error is not None:
                return error
            result = A.answer(table, p, {c: self._trace(p["round_id"], c) for c in p["cases"]})
            ab["state_queries"] += 1
            self.persist()
            self.audit({"operation": "state_query", "round": p["round_id"], "cases": p["cases"],
                        "names": sorted(p["names"]), "t": p["t"]})
            return {**result, "state_queries": ab["state_queries"]}
        if op == "save_state" and A.STATE_OPS:
            rounds = self._completed()
            if set(args) != {"round_id", "case", "t"}:
                return {"error": "save_state takes round_id, case and t", "rounds": list(rounds)}
            i, case, t = args["round_id"], args["case"], args["t"]
            if type(i) is not int or i not in rounds:
                return {"error": "unknown round_id (a completed round)", "rounds": list(rounds)}
            if type(case) is not int or case not in rounds[i]:
                return {"error": "unknown case", "cases": rounds[i]}
            if type(t) not in (int, float) or not math.isfinite(t):
                return {"error": "t is a time in seconds"}
            trace = self._trace(i, case)
            at = [k for k, x in enumerate(trace["t"]) if x <= t + 1e-9]
            if not at:
                return {"error": "no telemetry sample at or before t", "first_t": trace["t"][0] if trace["t"] else None}
            k = at[-1]
            point = trace["t"][k]
            row = s["rounds"][i]
            name = f"s{ab['next_handle']}"
            entry = {"handle": name, "round_id": i, "case": case, "t": point, "digest": trace["digest"][k],
                     "schedule": [seg for seg in row["schedule"] if seg[0] < point - 1e-9]}
            ab["next_handle"] += 1
            ab["saves"] += 1
            ab["handles"] = (ab["handles"] + [entry])[-A.MAX_HANDLES:]
            self.persist()
            self.audit({"operation": "save_state", "handle": name, "round": i, "case": case, "t": point})
            return {"handle": name, "round_id": i, "case": case, "t": point, "saves": ab["saves"]}
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
            ab["handles"] = [h for h in ab["handles"] if h is not entry] + [entry]   # most recently used last
            ab["pending"] = entry
            ab["_loaded"] = entry   # the digest check of the next deployment needs it even after the LRU drops it
            ab["loads"] += 1
            self.persist()
            self.audit({"operation": "load_state", "handle": entry["handle"]})
            return {"loaded": entry["handle"], "case": entry["case"], "t": entry["t"], "loads": ab["loads"],
                    "next_deployment": f"case {entry['case']} from t = {entry['t']} s, the deployed policy from there"}
        raise ValueError("Unknown operation")

    def ablation_fields(self, final, selected):
        """final.json's ablation fields (diagnostics and counts; the verdict never reads them)."""
        s = self.state
        ab = s["ablation"]
        t0 = (s["deadline"] or time.time()) - self.wall
        out = {}
        if A.HIDE_SUCCESS:
            ok = []
            for r in s["rounds"]:
                if r["status"] != "completed":
                    continue
                try:
                    cases = self._completed()[r["id"]]
                    if all(json.loads((self.root / f"round-{r['id']}" / f"case-{c}" / "record.json").read_text())
                           ["metrics"]["success"] for c in cases):
                        ok.append(r["id"])
                except (OSError, ValueError, KeyError):
                    pass
            out.update(
                success_signal="hidden",
                ended_by="finish" if ab["ended_by"] in ("finish", "seal") or s["sealed"] else "timeout",
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
                                           "cases": ([r["start"]["case"]] if r.get("start") else
                                                     list(range(len(self.instance["bank"]["adaptation"])))),
                                           **({"from": r["start"]} if r.get("start") else {}),
                                           "t_start_s": round(r["started_at"] - t0, 3),
                                           "t_end_s": round(r["completed_at"] - t0, 3) if r.get("completed_at") else None,
                                           "ended": r["status"]} for r in rounds],
                load_mismatches=[r["id"] for r in rounds if r.get("load_verified") is False],
            )
            if selected is not None:
                loaded = sum(1 for r in rounds if r["id"] <= selected["id"] and r.get("start"))
                first = final["success"] and selected["id"] < A.STANDARD_ROUNDS and loaded == 0
                if final["success"]:
                    out.update(resets_at_success=max(0, selected["id"] + 1 - A.STANDARD_ROUNDS),
                               loads_at_success=loaded)
            else:
                first = False
            out["first_success"] = int(bool(first))
        return out
