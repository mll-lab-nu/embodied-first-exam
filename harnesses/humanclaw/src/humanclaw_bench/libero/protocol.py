"""Durable, single-owner execution of the common robot tool protocol.

The journal guarantees at-most-once execution, including after a worker crash.
A started request without a committed result is indeterminate, never replayed.
"""
from __future__ import annotations

from concurrent.futures import Future
import contextvars
import hashlib
import json
from pathlib import Path
import queue
import sqlite3
import threading
from typing import Any

from humanclaw_bench.experiments.recorder import event, span
from humanclaw_bench.harnesses.services import trace_payload


PROTOCOL_VERSION = "libero_tools_v1"


def digest(value: Any) -> str:
    """Hash canonical JSON for stable capability and request identities."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def tool_definitions(catalog: list[dict]) -> list[dict]:
    """Add transport fields to the *same* upstream tool schema for all callers."""
    definitions = []
    for original in catalog:
        spec = json.loads(json.dumps(original))
        schema = spec["parameters"]
        properties = schema.setdefault("properties", {})
        if {"request_id", "observation_id"} & properties.keys():
            raise ValueError("Upstream tool collides with reserved protocol fields")
        properties.update({
            "request_id": {"type": "string", "minLength": 1,
                           "description": "Unique ID for this operation. Reuse ONLY to retrieve the same operation."},
            "observation_id": {"type": "integer", "minimum": 0,
                               "description": "ID of the observation used to choose this operation. Never guess a newer ID."},
        })
        schema["required"] = list(dict.fromkeys(schema.get("required", []) +
                                                ["request_id", "observation_id"]))
        definitions.append({"name": spec["name"], "description": spec["description"],
                            "inputSchema": schema})
    return definitions


class ToolService:
    """Execute on the simulator owner thread; HTTP workers only submit futures."""

    def __init__(self, backend, run_id: str, directory: Path, *, max_calls=40,
                 max_control_steps=20000):
        """Bind a run to one environment owner and open its durable request journal."""
        self.backend, self.run_id = backend, run_id
        self.owner = threading.get_ident()
        self.catalog = {s["name"]: s for s in backend.catalog}
        self.definitions = tool_definitions(backend.catalog)
        self.max_calls, self.max_control_steps = max_calls, max_control_steps
        self.step = 0
        self.observation_id = 0
        self.done = False
        self.termination = "running"
        self.failure = None
        self.pending: queue.Queue = queue.Queue()
        self.provider_requests = {}
        self.db = sqlite3.connect(directory / "requests.sqlite")
        self.db.execute("PRAGMA journal_mode=PERSIST")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS requests (request_id TEXT PRIMARY KEY, "
                        "fingerprint TEXT NOT NULL, state TEXT NOT NULL, response TEXT)")
        # A new process may inspect an old journal, but cannot resume an unproven
        # physical state. Replay has a separate entry point.
        count = self.db.execute("SELECT count(*) FROM requests").fetchone()[0]
        if count:
            self.failure = "reopened_journal_requires_new_attempt"
        self.observation = backend.observe()

    @property
    def image(self):
        """Provide a compatible single-image view for existing native drivers."""
        from PIL import Image
        import base64, io
        return Image.open(io.BytesIO(base64.b64decode(self.observation["images"][0]["data"]))).copy()

    def initial_images(self):
        """Return the complete shared initial camera list."""
        return self.observation["images"]

    def initial_prompt(self):
        """Describe the task, public knowledge and common execution protocol."""
        return (f"Perform this LIBERO-Pro task: {self.backend.instruction}\n"
                f"run_id: {self.run_id}; observation_id: {self.observation_id}.\n"
                f"Episode limit: {self.max_calls} environment tool calls, "
                f"{self.max_control_steps} controller steps.\n"
                "Use the common robot tools for all perception and motion. Use a new request_id "
                "for each new operation and the observation_id you used to choose it. "
                "Wait for each operation's result before choosing a dependent action. "
                "A stale observation is rejected; observe again. An indeterminate execution "
                "must not be repeated. Call done when finished; the evaluator judges success "
                "privately after the harness ends. Camera images are ordered head_camera, wrist, "
                "followed by any explicitly requested additional view.\n"
                f"Robot state: {json.dumps(self.observation.get('proprioception', {}))}\n"
                f"Frozen public task knowledge:\n{self.backend.knowledge}")

    def submit(self, name, arguments):
        """Queue an HTTP-thread request for execution on the environment owner."""
        future = Future()
        self.pending.put((contextvars.copy_context(), name, arguments, future))
        return future

    def drain(self):
        """Execute queued requests with their original trace context."""
        self._assert_owner()
        while not self.pending.empty():
            context, name, arguments, future = self.pending.get_nowait()
            if future.cancelled():
                continue
            try:
                future.set_result(context.run(self.call_tool, name, arguments))
            except BaseException as exc:
                future.set_exception(exc)
                raise

    def _assert_owner(self):
        """Reject simulator execution from a thread that does not own EGL."""
        if threading.get_ident() != self.owner:
            raise RuntimeError("Robot execution must stay on its EGL/simulator owner thread")

    def _response(self, request, status, *, result=None, error=None, before=None, steps=0):
        """Build a uniform response with the current public observation."""
        return {"protocol": PROTOCOL_VERSION, "run_id": self.run_id,
                "request_id": request.get("request_id"), "tool_name": request.get("tool_name"),
                "status": status, "result": result, "error": error,
                "observation_id": self.observation_id, "observation_before": before,
                "observation": self.observation, "control_steps": steps,
                "done": self.done, "termination_reason": self.termination if self.done else None}

    def call_tool(self, name, arguments):
        """Convert function-tool arguments into the canonical request envelope."""
        args = dict(arguments) if isinstance(arguments, dict) else {}
        request = {"run_id": self.run_id, "request_id": args.pop("request_id", None),
                   "observation_id": args.pop("observation_id", None),
                   "tool_name": name, "arguments": args}
        return self.execute(request)

    def execute(self, request):
        """Validate, deduplicate and durably execute one public tool request."""
        self._assert_owner()
        event("tool.requested", kind="tool", name=str(request.get("tool_name")), data=request)
        rid = request.get("request_id")
        try:
            if set(request) != {"run_id", "request_id", "tool_name", "arguments", "observation_id"}:
                raise ValueError("Invalid request envelope")
            if request["run_id"] != self.run_id:
                raise ValueError("Wrong run_id")
            if not isinstance(rid, str) or not rid.strip() or len(rid) > 256:
                raise ValueError("A nonempty request_id of at most 256 characters is required")
            fingerprint = digest(request)
            previous = self.db.execute("SELECT fingerprint,state,response FROM requests WHERE request_id=?", (rid,)).fetchone()
            if previous:
                if previous[0] != fingerprint:
                    raise ValueError("request_id_conflict")
                event("tool.deduplicated", kind="tool", name=request["tool_name"], data={"request_id": rid})
                if previous[2] is not None:
                    return json.loads(previous[2])
                return self._response(request, "indeterminate", error="Previously started operation has no committed result; start a new episode")
            if self.failure:
                raise ValueError(str(self.failure))
            if self.done:
                raise ValueError("Episode has ended")
            if request["tool_name"] not in self.catalog:
                raise ValueError("Unknown public tool")
            if type(request["observation_id"]) is not int or request["observation_id"] != self.observation_id:
                raise ValueError(f"stale_observation: current observation_id={self.observation_id}")
            from jsonschema import Draft202012Validator
            Draft202012Validator(self.catalog[request["tool_name"]]["parameters"]).validate(request["arguments"])
        except (ValueError, TypeError) as exc:
            event("tool.rejected", kind="tool", name=str(request.get("tool_name")), data={"request": request, "error": str(exc)})
            return self._response(request, "rejected", error=str(exc))
        except Exception as exc:
            # Schema failures are pre-execution and safe; no physical side effect.
            if type(exc).__module__.startswith("jsonschema"):
                event("tool.rejected", kind="tool", name=str(request.get("tool_name")),
                      data={"request": request, "error": str(exc)})
                return self._response(request, "rejected", error=str(exc))
            raise

        if self.step >= self.max_calls or self.backend.control_steps >= self.max_control_steps:
            self.done, self.termination = True, "budget_exhausted"
            event("tool.rejected", kind="tool", name=request["tool_name"],
                  data={"request": request, "error": self.termination})
            return self._response(request, "rejected", error=self.termination)
        self.db.execute("INSERT INTO requests VALUES (?,?,?,NULL)", (rid, fingerprint, "started"))
        self.db.commit()  # Durable intent precedes ANY physical execution.
        before, start_steps = self.observation_id, self.backend.control_steps
        with span(request["tool_name"], kind="tool", input=request,
                  attributes={"catalog_hash": self.backend.catalog_hash, "request_id": rid}) as operation:
            interrupted = None
            try:
                result = self.backend.dispatch(request["tool_name"], request["arguments"])
                self.step += int(request["tool_name"] != "done")
                self.observation_id += 1
                self.observation = self.backend.observe()
                if request["tool_name"] == "done":
                    self.done, self.termination = True, "agent_done"
                elif self.step >= self.max_calls:
                    self.done, self.termination = True, "tool_budget"
                elif self.backend.control_steps >= self.max_control_steps:
                    self.done, self.termination = True, "control_budget"
                failed = isinstance(result, dict) and result.get("ok") is False
                response = self._response(request, "failed" if failed else "completed", result=result,
                                          before=before, steps=self.backend.control_steps-start_steps)
                if failed:
                    operation.fail(result)
                operation.set_output(trace_payload(response))
            except BaseException as exc:
                self.failure = str(exc)
                known_budget = type(exc).__name__ == "ControlBudgetReached"
                self.done, self.termination = True, "control_budget" if known_budget else "execution_indeterminate"
                response = self._response(request, "failed" if known_budget else "indeterminate", error=f"{type(exc).__name__}: {exc}",
                                          before=before, steps=self.backend.control_steps-start_steps)
                operation.fail(exc)
                if not isinstance(exc, Exception):
                    interrupted = exc
            try:
                self.db.execute("UPDATE requests SET state=?,response=? WHERE request_id=?",
                                (response["status"], json.dumps(response, allow_nan=False), rid))
                self.db.commit()
            except Exception as exc:
                # Physical execution may have finished, but its result is not
                # durably acknowledged. Preserve the committed intent and stop.
                try:
                    self.db.rollback()
                except sqlite3.Error:
                    pass
                self.failure = "result_commit_failed"
                self.done, self.termination = True, "execution_indeterminate"
                raise RuntimeError("Tool result could not be committed; never retry execution") from exc
            if interrupted is not None:
                raise interrupted
            return response

    def close(self):
        """Fail pending requests when the episode session closes."""
        while not self.pending.empty():
            _, _, _, future = self.pending.get_nowait()
            if not future.done():
                future.set_exception(RuntimeError("Episode session closed"))

    def shutdown(self):
        """Close pending futures and release the durable request journal."""
        self.close()
        self.db.close()


def mcp_result(response):
    """Expose response text and images using standard MCP content blocks."""
    public = {k: v for k, v in response.items() if k != "observation"}
    observation = response.get("observation") or {}
    public["proprioception"] = observation.get("proprioception", {})
    public["camera_names"] = observation.get("camera_names", [])
    return {"isError": response["status"] in {"rejected", "failed", "indeterminate"},
            "content": [{"type": "text", "text": json.dumps(public, ensure_ascii=False)},
                        *observation.get("images", [])]}
