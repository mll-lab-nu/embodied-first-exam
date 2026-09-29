"""A trial owns agent memory and budgets; disposable episodes own physics."""
import copy
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import secrets
import shutil
import threading
import time
import traceback

from topogym.agent_bridge.policy import integer
from topogym.agent_bridge.session import write_json
from .agents import create_agent, validate_decision
from .episode import Episode
from .profiles import profile
from .suite import load_preset
from .token_budget import TokenBudgetExhausted


class Trial:
    def __init__(self, job):
        self.job, self.profile = job, profile(job["agent"])
        self.public, self.private = Path(job["public"]), Path(job["private"])
        self.started = time.monotonic()
        self.deadline = self.started + job.get("worker_timeout_s", 3600)
        self.lock, self.cache = threading.RLock(), {}
        self.budget, self.episode = None, None
        self.status, self.reason, self.closed = "running", "", False
        self.resets = self.ticks = self.segments = self.api_calls = self.revision = 0
        self.episode_index = 0
        self.records, self.events = [], []
        self.execution_accounting_complete = True
        self.preset = load_preset(job["preset"])
        self.max_resets = job.get("max_resets", 2) if self.profile["reset_policy"] == "same_preset" else 0
        self.initial_audit = job.get("expected_initial")

    def start(self):
        self._start_episode()
        write_json(self.public / "task_spec.json", self.task)
        write_json(self.public / "capabilities.json", self.capabilities())
        shutil.copyfile(Path(__file__).with_name("env_sdk.py"), self.public / "topogym_env.py")
        self._event("trial_started", profile=self.profile, preset_sha256=self.preset["sha256"])
        return self

    def _start_episode(self):
        self.episode = Episode(self.job, self.episode_index, self.initial_audit, self.deadline)
        initial = self.episode.initial
        self.task, self.simulator = initial["task"], initial["simulator"]
        if self.profile["access_mode"] == "simulator" and not self.simulator:
            raise ValueError("This adapter has no simulator state API; select a supported task")
        self.initial_audit = self.initial_audit or initial["audit"]["initial_audit"]
        self.latest, self.episode_state = initial["media"], initial["state"]
        self.records.append(dict(episode_id=self.episode_index, ticks=0, segments=0,
            state=self.episode_state, **initial["audit"], physics_qualified=initial["physics_qualified"]))
        self._update_status()

    def capabilities(self):
        return dict(schema="topogym.environment.v2", **self.profile, max_resets=self.max_resets,
            methods=["describe", "observe", "render", "step", "finish"] +
                (["reset"] if self.max_resets else []) +
                (["get_state", "get_pose", "list_entities"] if self.profile["access_mode"] == "simulator" else []),
            simulator=self.simulator if self.profile["access_mode"] == "simulator" else {},
            state_writes=False, scene_resampling=False, reset_scope="same frozen preset",
            max_steps_per_call=self.job["max_steps"], max_total_steps=self.job["max_total_steps"],
            max_segments=self.job["max_segments"], max_api_calls=self.job.get("max_api_calls", 1000))

    def snapshot(self):
        index = self.episode_index
        media_path = f"episodes/episode_{index}/segment_{self.latest['segment']}.json"
        images = [f"episodes/episode_{index}/"+item["path"] for item in self.latest["model_inputs"]]
        return dict(schema="topogym.trial.v2", **self.profile, status=self.status, reason=self.reason,
            preset_sha256=self.preset["sha256"],
            episode_id=index, episode_state=self.episode_state, state_revision=self.revision,
            episode_tick=self.records[-1]["ticks"], total_ticks=self.ticks, total_segments=self.segments,
            resets=self.resets, max_resets=self.max_resets, api_calls=self.api_calls,
            remaining_steps=max(0, self.job["max_total_steps"]-self.ticks),
            remaining_wall_seconds=max(0, self.deadline-time.monotonic()),
            token_budget=self.budget.snapshot() if self.budget else None,
            latest_manifest=media_path, images=images)

    def _event(self, kind, **details):
        entry = {**self.snapshot(), **details, "event_id": len(self.events), "event": kind,
                 "wall_seconds": time.monotonic()-self.started}
        self.events.append(entry)
        for root in (self.public, self.private):
            with (root / "events.jsonl").open("a") as stream:
                stream.write(json.dumps(entry, allow_nan=False)+"\n")
            write_json(root / "trial.json", self.snapshot())

    def _update_status(self):
        if self.episode_state == "succeeded":
            self.status, self.reason = "succeeded", "Environment evaluator confirmed success"
        elif self.episode_state == "failed" and self.resets >= self.max_resets:
            self.status, self.reason = "task_failed", "Episode failed; no resets remain"
        elif self.ticks >= self.job["max_total_steps"] or self.segments >= self.job["max_segments"]:
            self.status, self.reason = "limit_reached", "Trial action budget exhausted"

    def _check_limits(self):
        if self.closed:
            raise ValueError("Trial is closed")
        if time.monotonic() >= self.deadline:
            if self.status == "running":
                self.status, self.reason = "limit_reached", "Trial wall-time budget exhausted"
            raise ValueError("Trial wall-time budget exhausted")
        if self.budget and self.status == "running":
            state = self.budget.snapshot()
            if state["blocked"] or state["used"] >= state["limit"]:
                self.status = "token_budget_exhausted" if not state["blocked"] or state["blocked"] == "token_budget_exhausted" else "pipeline_error"
                self.reason = "Token budget unavailable; inspect operator ledger"
                raise ValueError(self.reason)
        if self.api_calls >= self.job.get("max_api_calls", 1000):
            if self.status == "running":
                self.status, self.reason = "limit_reached", "Trial API call budget exhausted"
            raise ValueError("Trial API call budget exhausted")

    def dispatch(self, request):
        with self.lock:
            if not isinstance(request, dict) or set(request)-{"method", "params", "request_id", "expected_revision"}:
                raise ValueError("Invalid environment request")
            request_id = request.get("request_id")
            if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
                raise ValueError("request_id must contain 1..128 characters")
            fingerprint = json.dumps(request, sort_keys=True, allow_nan=False)
            if request_id in self.cache:
                previous, result = self.cache[request_id]
                if previous != fingerprint:
                    raise ValueError("Conflicting request_id")
                if "error" in result:
                    raise ValueError(result["error"])
                return copy.deepcopy(result)
            self._check_limits()
            self.api_calls += 1
            method, params = request.get("method"), request.get("params", {})
            if not isinstance(method, str) or not isinstance(params, dict):
                raise ValueError("Expected a method name and params object")
            try:
                allowed = dict(describe=set(), observe=set(), render=set(), list_entities=set(),
                    get_state={"fields"}, get_pose={"entity", "frame"}, step={"action", "steps"}, reset=set(), finish=set())
                if method not in allowed or set(params)-allowed[method]:
                    raise ValueError("Unsupported method or parameters")
                if method in ("get_state", "get_pose", "list_entities") and self.profile["access_mode"] != "simulator":
                    raise ValueError("State queries are unavailable in the RGB profile")
                if method in ("step", "reset", "finish"):
                    if type(request.get("expected_revision")) is not int or request["expected_revision"] != self.revision:
                        raise ValueError("Stale state revision; inspect the current episode before acting")
                    if self.status != "running":
                        raise ValueError("Trial has ended: " + self.status)
                data = {}
                if method == "describe":
                    data = dict(task=self.task, capabilities=self.capabilities())
                elif method in ("observe", "render"):
                    # Last synchronized capture: physics is paused between calls.
                    data = dict(observation=self.episode.call("get_state", {}) if self.profile["access_mode"] == "simulator" else {})
                elif method == "list_entities":
                    data = dict(entities=self.simulator.get("pose_entities", []))
                elif method in ("get_state", "get_pose"):
                    data = self.episode.call(method, params)
                elif method == "step":
                    if self.episode_state != "ready":
                        raise ValueError("Episode ended; reset if permitted before further actions")
                    steps = integer(params.get("steps", 1), "steps", 1,
                                    min(self.job["max_steps"], self.job["max_total_steps"]-self.ticks))
                    if not isinstance(params.get("action"), dict):
                        raise ValueError("action must be an object")
                    try:
                        result = self.episode.call("step", dict(action=params["action"], steps=steps),
                            max_steps=steps, request_id=request_id)
                    except ValueError:
                        raise  # Preflight rejection; no physics was executed.
                    except Exception:
                        self.execution_accounting_complete = False
                        raise
                    old = self.records[-1]
                    self.ticks += result["tick"]-old["ticks"]
                    self.segments += result["segments"]-old["segments"]
                    old.update(ticks=result["tick"], segments=result["segments"], state=result["state"])
                    self.episode_state, self.latest = result["state"], result["media"]
                    self.revision += 1
                    self._update_status()
                    if result["execution_error"]:
                        self.execution_accounting_complete = False
                        self.status, self.reason = "pipeline_error", "Execution/recording failed; see operator episode logs"
                    data = dict(executed_steps=self.latest["executed_steps"])
                elif method == "reset":
                    if self.resets >= self.max_resets:
                        raise ValueError("Reset is disabled or the reset budget is exhausted")
                    self.episode.close()
                    self.resets += 1
                    self.episode_index += 1
                    self.revision += 1
                    self._start_episode()
                    data = dict(restored_same_preset=True)
                elif method == "finish":
                    self.status, self.reason = "agent_stopped", "Agent ended this trial"
                    self.revision += 1
                result = dict(self.snapshot(), data=data)
                self.cache[request_id] = (fingerprint, copy.deepcopy(result))
                self._event("tool_completed", method=method, request_id=request_id, params=params, response=result)
                return result
            except ValueError as exc:
                self.cache[request_id] = (fingerprint, dict(error=str(exc)))
                self._event("tool_rejected", method=method, request_id=request_id, error=str(exc))
                raise
            except Exception:
                self.status, self.reason = "pipeline_error", "Environment operation failed; see operator logs"
                (self.private / "environment_error.txt").write_text(traceback.format_exc())
                self.cache[request_id] = (fingerprint, dict(error=self.reason))
                self._event("tool_failed", method=method, request_id=request_id)
                raise RuntimeError(self.reason) from None

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            if self.episode:
                self.episode.close()
            if self.records:
                # Recover the last durable counters after a worker/encoder crash.
                # Missing native-step receipts are explicitly marked incomplete.
                for record in self.records:
                    path = self.private / "episodes" / f"episode_{record['episode_id']}" / "execution/session.json"
                    if path.is_file():
                        state = json.loads(path.read_text())
                        record.update(ticks=state["tick"], segments=len(state["segments"]), state=state["state"])
                self.ticks = sum(record["ticks"] for record in self.records)
                self.segments = sum(record["segments"] for record in self.records)
                self._event("trial_ended")
                write_json(self.private / "episodes.json", self.records)
                write_json(self.public / "trajectory.json", dict(schema="topogym.tool_trajectory.v1",
                    profile=self.profile, events=self.events,
                    note="Environment tools and agent decisions; raw model events are in operator call logs. Not ATIF."))


class EnvironmentServer:
    def __init__(self, trial):
        self.trial, self.token = trial, secrets.token_urlsafe(32)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(10)

            def log_message(self, *_):
                pass

            def do_POST(self):
                try:
                    if self.path != "/v1/environment" or not hmac.compare_digest(
                            self.headers.get("Authorization", ""), "Bearer "+owner.token):
                        self.reply(401, dict(error="Unauthorized environment request"))
                        return
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 131072:
                        raise ValueError("Invalid request size")
                    request = json.loads(self.rfile.read(length))
                    self.reply(200, owner.trial.dispatch(request))
                except (ValueError, TypeError, KeyError) as exc:
                    self.reply(400, dict(error=str(exc)))
                except Exception:
                    self.reply(500, dict(error="Environment operation failed; see operator logs"))

            def reply(self, status, payload):
                data = json.dumps(payload, allow_nan=False).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        # One persistent owner thread serializes physics and survives requests.
        # Linux parent-death signals follow the thread that spawns an episode;
        # a per-request spawning thread would kill a freshly reset episode as
        # soon as that HTTP request finishes.
        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1/environment"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)


def tool_prompt(trial):
    return (
        "Solve this TopoGym task using the live environment SDK. Use English. Physics pauses between actions.\n"
        "Read task_spec.json and capabilities.json. Write ordinary Python in scratch/; import connect from topogym_env. "
        "Use env = connect(); env.describe(), observe()/render(), step(action, steps=N), and finish(). "
        "Only simulator access enables list_entities(), get_state(fields=None), get_pose(entity, frame='world'). "
        "Responses contain data plus episode_id, state_revision, budget, images and latest_manifest. "
        "All file paths are relative to /workspace. Use your image viewer on returned image paths; a filename alone is not a visual observation.\n"
        "Run with PYTHONPATH=/workspace python3 scratch/policy.py. The SDK uses injected endpoint credentials. "
        "All scripts connect to the same live worker; Python loops and libraries are allowed in your workspace. "
        "Every physical action must use env.step. Do not alter physics, initial presets or the evaluator. "
        "A step response reports actual executed_steps and synchronized media. Observe new feedback before planning subsequent actions.\n"
        "reset(), when enabled in capabilities, restores the SAME frozen initial state. It starts a new physical episode, "
        "retaining your conversation, files, and cumulative token/step/segment/wall-time budgets. "
        "An ended episode needs reset before more actions; a succeeded or exhausted trial cannot be reset. "
        "The SDK rejects stale state revisions; use observe() to inspect the current state before retrying.\n"
        "Media: episodes/episode_E/segment_0.mp4 is that episode's static initial view; segment_N.mp4 records action N. "
        "Each camera has its own MP4; segment_N.json indexes frames/ticks. Previous episodes remain available. "
        "Do not read other trials, private files, repository source or demonstrations. Scratch is writable; inputs are read-only.\n"
        "Use terminal tools to act directly. When finished return JSON {kind:'stop', code:'', paths:[], reason:'...'} "
        "using valid JSON double quotes. A final segment decision is unsupported in this interaction mode. "
        "Only the environment evaluator declares success.\n"
        f"Profile: {json.dumps(trial.capabilities())}\nTask: {json.dumps(trial.task)}\n"
        f"Current trial: {json.dumps(trial.snapshot())}\n"
    )


def run_tool_repeat(job):
    public, private = Path(job["public"]).resolve(), Path(job["private"]).resolve()
    public.mkdir(parents=True, exist_ok=False)
    private.mkdir(parents=True, exist_ok=False)
    (public / "scratch").mkdir()
    result = dict(agent_id=job["agent"]["id"], provider=job["agent"]["provider"], repeat=job["repeat"],
        input_mode=profile(job["agent"])["access_mode"], **profile(job["agent"]),
        status="pipeline_error", success=False, calls=0, usage=[], usage_complete=True,
        ticks=0, segments=0, resets=0, observation_isolation="prompt_policy", physics_qualified=False)
    trial = agent = server = None
    started = time.monotonic()
    try:
        trial = Trial(dict(job, public=str(public), private=str(private)))
        result.update(task_id=trial.preset["task_id"], variant_id=trial.preset["variant_id"], preset_sha256=trial.preset["sha256"])
        trial.start()
        result.update({k: v for k, v in trial.records[0].items() if k.startswith("initial_")})
        result["physics_qualified"] = trial.records[0]["physics_qualified"]
        server = EnvironmentServer(trial)
        config = dict(job["agent"], token_limit=job.get("token_limit", 3_000_000),
            max_output_tokens=job.get("max_output_tokens", 8192), interaction="tools",
            environment_url=server.url, environment_token=server.token)
        agent = create_agent(config, public, private)
        trial.budget = getattr(agent, "budget", None)
        result["observation_isolation"] = agent.isolation
        for number in range(1, job["max_calls"]+1):
            if trial.status != "running":
                break
            request = dict(prompt=tool_prompt(trial), images=trial.snapshot()["images"], call=number, public_dir=str(public))
            write_json(private / f"call_{number}.request.json", request)
            if hasattr(agent, "config"):
                agent.config["timeout_s"] = max(.01, min(config.get("timeout_s", 600), trial.deadline-time.monotonic()))
            result["calls"] = number
            decision, usage = agent.decide(request, number)
            result["usage"].append(usage)
            result["usage_complete"] &= usage is not None
            write_json(private / f"call_{number}.decision.json", decision)
            trial._event("agent_decision", call=number, decision=decision, usage=usage)
            decision = validate_decision(decision)
            if decision["kind"] == "stop":
                if trial.status == "running":
                    trial.status, trial.reason = "agent_stopped", "Agent ended this trial"
                break
            if decision["kind"] != "inspect":
                raise ValueError("Tools interaction requires acting through the SDK, then a stop decision")
            # A new turn reattaches the current synchronized views. The agent can
            # inspect all historical frames directly through its terminal tools.
        else:
            if trial.status == "running":
                trial.status, trial.reason = "limit_reached", "Agent call budget exhausted"
        result.update(status=trial.status, success=trial.status == "succeeded", reason=trial.reason)
    except TokenBudgetExhausted as exc:
        result.update(status="token_budget_exhausted", success=False, reason=str(exc))
    except Exception as exc:
        result.update(status="pipeline_error", success=False, reason=f"{type(exc).__name__}: {exc}")
        (private / "error.txt").write_text(traceback.format_exc())
    finally:
        if trial:
            trial.status, trial.reason = result["status"], result.get("reason", "")
            trial.close()  # Reject late/background commands before closing model transport.
        if server:
            server.close()
        if agent and hasattr(agent, "close"):
            agent.close()
        if trial:
            result.update(ticks=trial.ticks, segments=trial.segments, resets=trial.resets, api_calls=trial.api_calls,
                execution_accounting_complete=trial.execution_accounting_complete,
                episodes=len(trial.records), first_episode_success=bool(trial.records and trial.records[0]["state"] == "succeeded"))
        budget = getattr(agent, "budget", None)
        result["token_budget"] = budget.snapshot() if budget else None
        result["usage_complete"] &= len(result["usage"]) == result["calls"]
        if budget:
            result["usage_complete"] = result["token_budget"]["usage_complete"]
        result["success_within_token_budget"] = bool(result["success"] and budget and result["usage_complete"]
            and not result["token_budget"]["over_budget"] and not result["token_budget"]["blocked"])
        result["success_physics_qualified"] = result["success"] and result["physics_qualified"]
        result["wall_seconds"] = time.monotonic()-started
        write_json(private / "result.json", result)
    return result
