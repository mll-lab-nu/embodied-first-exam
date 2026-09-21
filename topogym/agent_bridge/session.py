"""One process-lifetime episode. No resume, reset, checkpoint or undo API."""
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import threading
import time

from .budget import Budget
from .policy import compile_policy, integer
from .tool_policy import tool_policy, policy_prompt


def write_json(path, value):
    data = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as stream:
        stream.write(data)
        stream.flush()
        import os
        os.fsync(stream.fileno())
    temp.replace(path)


class Session:
    def __init__(self, factory, output, *, token_limit=2_000_000, mode="metered", max_steps=1000,
                 allow_internet=True):
        self.budget = Budget(token_limit, mode)
        self.tool_policy = tool_policy(allow_internet)
        self.public_assets = {}
        self.max_steps = integer(max_steps, "max_steps", 1, 10_000)
        self.root = Path(output).resolve()
        # Exclusive directory creation prevents accidental replay after a crash.
        self.root.mkdir(parents=True, exist_ok=False)
        self.lock = threading.RLock()
        self.execution_lock = threading.Lock()
        self.state, self.reason, self.tick = "initializing", "", 0
        self.segments, self.requests, self.spent_calls = [], {}, set()
        self.description, self.observation, self.latest = {}, {}, None
        self._persist()
        try:
            self.adapter = factory(self.root / "private_assets")
            self.description = self.adapter.describe()
            if self.description.get("goal_reference"):
                raise ValueError("Object reference data is not a public task input; infer configuration from episode observations")
            # Only textual basic metadata: visual object inputs come from this episode.
            for name, source in getattr(self.adapter, "public_assets", {}).items():
                if not re.fullmatch(r"[A-Za-z0-9_-]+\.(json|md)", name):
                    raise ValueError("Public task assets must be JSON/Markdown basic metadata; reference images are not permitted")
                target = self.root / "public_assets" / name
                target.parent.mkdir(exist_ok=True)
                shutil.copyfile(source, target)
                data = target.read_bytes()
                relative = target.relative_to(self.root).as_posix()
                self.public_assets[relative] = dict(path=relative, bytes=len(data),
                    sha256=hashlib.sha256(data).hexdigest())
            self.description["public_assets"] = list(self.public_assets.values())
            names = self.description["cameras"]
            if (len(names) < 2 or len(set(names)) != len(names) or
                    any(not re.fullmatch(r"[A-Za-z0-9_-]+", n) for n in names)):
                raise ValueError("Declare at least two uniquely named cameras")
            arms = self.description.get("robot", {}).get("arms", [])
            required = ({"cam_high", "cam_low", "cam_left_wrist", "cam_right_wrist"} if len(arms) == 2
                        else {"agentview", "front_oblique", "wrist"} if len(arms) == 1 else None)
            if required is not None and set(names) != required:
                raise ValueError("Robot tasks require all canonical views: three for one arm, four for two arms")
            period = self.description["control_dt_s"]
            if not isinstance(period, (int, float)) or not 0 < period < 100:
                raise ValueError("Invalid control period")
            folder = self.root / "initial"
            folder.mkdir()
            manifest = dict(kind="initial", frames=[])
            self._capture(folder, manifest)
            self.latest = "initial/manifest.json"
            self.state = "ready"
            self._verdict()
            self._persist()
        except Exception as exc:
            self.state, self.reason = "failed", f"Initialization failed: {exc}"
            self._persist()
            raise

    def snapshot(self):
        with self.lock:
            budget = self.budget.snapshot()
            return copy.deepcopy(dict(protocol="topogym.agent_bridge.v1", state=self.state,
                reason=self.reason, task=self.description, tool_policy=self.tool_policy, tick=self.tick,
                next_segment=len(self.segments)+1, max_segment_steps=self.max_steps,
                budget=budget, observation=self.observation, latest_manifest=self.latest,
                segments=self.segments, no_rollback=True,
                success_within_budget=(self.state == "succeeded" and budget["exact"] and
                                       not budget["over_budget"])))

    def prompt(self):
        s = self.snapshot()
        b = s["budget"]
        if b["mode"] == "manual":
            balance = (f"已上报估算用量 {b['used']:,}；估算剩余 {b['remaining']:,} tokens，真实余额未知。"
                       if b["calls"] else "Token 用量未测量，真实剩余 tokens 未知；不能把未记账当成零消耗。")
        else:
            balance = f"你还剩 {b['remaining']:,} tokens（扣除已记账和当前预留）。"
        return (f"TopoGym segmented episode. State: {s['state']}.\n"
                f"Token budget: {b['limit']:,}; ledger used: {b['used']:,}; reserved: {b['reserved']:,}. "
                f"Accounting mode: {b['mode']}. {balance}\n"
                + ("Manual accounting includes reported estimates only. Without usage reports, the displayed balance "
                   "does not measure your Codex/ChatGPT session and cannot certify a 2M-token run.\n"
                   if b["mode"] == "manual" else "") +
                "所有动作不可撤销，不能回滚 simulator state。\n"
                + policy_prompt(self.tool_policy) +
                "Write a Python action segment: assignments, for/range, lists/dicts/indexing, "
                "numeric + - * / and env.step(action, steps=N). obs is the segment-start observation. "
                "No imports, functions, while, arbitrary calls or simulator access. "
                f"Maximum {self.max_steps} control ticks per segment. "
                "The environment stops early on success/failure. All camera frames at every control tick "
                "are preserved; you may inspect any historical frame. Physics substeps are not camera frames.\n"
                f"Next expected_segment: {s['next_segment']}. Latest complete/partial feedback: {self.latest}.\n"
                f"Task/action contract: {json.dumps(self.description, ensure_ascii=False)}\n"
                f"Public observation: {json.dumps(self.observation, ensure_ascii=False)}\n"
                f"History manifests: {json.dumps([x['manifest'] for x in self.segments])}\n")

    def _persist(self):
        with self.lock:
            write_json(self.root / "session.json", self.snapshot())
            (self.root / "next_prompt.txt").write_text(self.prompt(), encoding="utf-8")

    def _event(self, kind, **fields):
        with (self.root / "events.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(dict(time=time.time(), event=kind, tick=self.tick, **fields),
                               ensure_ascii=False, allow_nan=False) + "\n")
            f.flush()

    def _capture(self, folder, manifest):
        images = self.adapter.render()
        if set(images) != set(self.description["cameras"]):
            raise RuntimeError("Incomplete camera set")
        observation = self.adapter.observe()
        frame = dict(index=len(manifest["frames"]), tick=self.tick,
                     time_s=self.tick*self.description["control_dt_s"], cameras={}, observation=observation)
        for name, data in images.items():
            if not isinstance(data, bytes) or not data.startswith(b"\x89PNG\r\n\x1a\n"):
                raise RuntimeError(f"{name} must supply PNG bytes")
            target = folder / name / f"{frame['index']:06d}.png"
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(data)
            frame["cameras"][name] = dict(path=target.relative_to(self.root).as_posix(),
                sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
        manifest["frames"].append(frame)
        write_json(folder / "manifest.json", manifest)
        with self.lock:
            self.observation = observation

    def _verdict(self):
        verdict = self.adapter.evaluate()
        if verdict.get("status") not in ("running", "succeeded", "failed"):
            raise RuntimeError("Adapter returned an invalid verdict")
        if verdict["status"] != "running":
            self.state, self.reason = verdict["status"], str(verdict.get("reason", ""))
        return verdict

    def usage(self, operation, **payload):
        with self.lock:
            if self.state == "executing":
                raise ValueError("Cannot change accounting while a segment executes")
            if operation in ("reserve", "estimate") and self.state != "ready":
                raise ValueError(f"Session is {self.state}")
            if operation not in ("reserve", "progress", "complete", "estimate"):
                raise ValueError("Unknown usage operation")
            # Raw provider receipts are retained for audit, outside public media.
            response = payload.get("response")
            getattr(self.budget, operation)(**payload)
            if response is not None:
                folder = self.root / "private_usage"
                folder.mkdir(exist_ok=True)
                digest = hashlib.sha256(payload["call_id"].encode()).hexdigest()
                target = folder / f"{digest}.json"
                if not target.exists():
                    write_json(target, response)
            b = self.budget.snapshot()
            exceeded = any(c.get("reservation_exceeded") for c in self.budget.calls.values())
            if exceeded:
                self.state, self.reason = "failed", "Provider usage exceeded its reservation; budget contract violated"
            elif b["used"] >= b["limit"] and self.state == "ready":
                self.state, self.reason = "budget_exhausted", "Token budget exhausted"
            self._event("usage_"+operation, call_id=payload["call_id"], used=b["used"], reserved=b["reserved"])
            self._persist()
            return self.snapshot()

    def finish(self, reason="Agent stopped", outcome="failed"):
        with self.lock:
            if outcome not in ("failed", "budget_exhausted"):
                raise ValueError("Only the evaluator can declare success")
            if self.state == "executing":
                raise ValueError("Wait for the current segment to finish")
            if self.state == "ready":
                self.state, self.reason = outcome, str(reason)
                self._event("finished", reason=self.reason)
                self._persist()
            return self.snapshot()

    def submit(self, *, request_id, expected_segment, code, call_id=None):
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
            raise ValueError("request_id must contain 1..128 characters")
        integer(expected_segment, "expected_segment", 1)
        fingerprint = hashlib.sha256(json.dumps([expected_segment, code, call_id], allow_nan=False).encode()).hexdigest()
        if not self.execution_lock.acquire(blocking=False):
            raise ValueError("Another segment is executing")
        try:
            with self.lock:
                if request_id in self.requests:
                    previous = self.requests[request_id]
                    if previous["fingerprint"] != fingerprint:
                        raise ValueError("Conflicting request_id")
                    return copy.deepcopy(previous["result"])
                if self.state != "ready":
                    raise ValueError(f"Session is {self.state}; actions are disabled")
                if expected_segment != len(self.segments)+1:
                    raise ValueError("Stale expected_segment; read the current prompt")
                if any(c["state"] == "pending" for c in self.budget.calls.values()):
                    raise ValueError("Finalize pending usage before executing actions")
                if self.budget.mode == "metered":
                    c = self.budget.calls.get(call_id, {})
                    if c.get("state") != "complete" or call_id in self.spent_calls or c["usage"]["total_tokens"] == 0:
                        raise ValueError("Each segment needs an unused, nonzero provider usage receipt")
                actions = compile_policy(code, self.observation, self.max_steps)
                # Validate the entire action list before touching controller targets.
                json.dumps(actions, allow_nan=False)
                for action in actions:
                    self.adapter.validate_action(action)
                folder = self.root / f"segment_{expected_segment:03d}"
                folder.mkdir()
                (folder / "policy.py").write_text(code, encoding="utf-8")
                (folder / "prompt.txt").write_text(self.prompt(), encoding="utf-8")
                manifest = dict(segment=expected_segment, request_id=request_id, call_id=call_id,
                    code_sha256=hashlib.sha256(code.encode()).hexdigest(), requested_steps=len(actions),
                    executed_steps=0, attempted_steps=0, status="executing", frames=[], error=None)
                write_json(folder / "manifest.json", manifest)
                self.latest = f"{folder.name}/manifest.json"
                self.segments.append(dict(segment=expected_segment, manifest=self.latest, status="executing"))
                self.state = "executing"
                if call_id is not None:
                    self.spent_calls.add(call_id)
                self._event("segment_started", segment=expected_segment, request_id=request_id)
                self._persist()
            try:
                self._capture(folder, manifest)
                for action in actions:
                    manifest["attempted_steps"] += 1
                    write_json(folder / "manifest.json", manifest)
                    self.adapter.step(action)
                    with self.lock:
                        self.tick += 1
                    manifest["executed_steps"] += 1
                    self._capture(folder, manifest)
                    with self.lock:
                        verdict = self._verdict()
                        self._persist()
                    if verdict["status"] != "running":
                        break
            except Exception as exc:
                # State may already have advanced. Preserve every recorded frame and stop.
                with self.lock:
                    self.state, self.reason = "failed", f"Execution/observation failed: {type(exc).__name__}: {exc}"
                manifest["error"] = self.reason
            with self.lock:
                if self.state == "executing":
                    self.state = "ready"
                manifest.update(status=self.state, end_tick=self.tick, budget=self.budget.snapshot())
                write_json(folder / "manifest.json", manifest)
                self.segments[-1].update(status=self.state, executed_steps=manifest["executed_steps"])
                result = dict(manifest=self.latest, segment=expected_segment, state=self.state,
                              executed_steps=manifest["executed_steps"], error=manifest["error"])
                self.requests[request_id] = dict(fingerprint=fingerprint, result=result)
                write_json(self.root / "requests.json", self.requests)
                self._event("segment_finished", **result)
                self._persist()
                return copy.deepcopy(result)
        finally:
            self.execution_lock.release()

    def artifact(self, relative):
        # Public references are explicit; private assets/usage stay off this API.
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root) or not path.is_file():
            raise ValueError("Unknown artifact")
        parts = path.relative_to(self.root).parts
        if path.relative_to(self.root).as_posix() in self.public_assets:
            return path
        if (len(parts) < 2 or not (parts[0] == "initial" or re.fullmatch(r"segment_[0-9]+", parts[0]))
                or path.suffix not in (".png", ".json", ".txt", ".py")):
            raise ValueError("Artifact is not public")
        return path
