"""Run the installed native harness as one persistent session per episode."""

from __future__ import annotations

from collections import deque
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import shutil
import signal
import subprocess
import threading
import time
from typing import Any

from humanclaw_bench.experiments.integration import resolved_model_settings
from humanclaw_bench.experiments.recorder import event, get_recorder, span
from humanclaw_bench.vlm.endpoints import configured_base_url, validate_base_url
from .environment import EnvironmentBridge, image_content
from .native_events import NativeEvents
from .services import LocalServices
from .pi_adaptive import PACKAGE as PI_ADAPTIVE_PACKAGE, adaptive_enabled, package_identity, resolve_profile


EXTERNAL_HARNESSES = {"codex", "pi"}


def load_harness_config(path: str | Path | None) -> dict[str, Any]:
    """Load explicit runtime settings and reject inline credential fields."""
    if path is None:
        raise ValueError("Codex/Pi require --harness-config (see docs/NATIVE_HARNESSES.md)")
    value = json.loads(Path(path).expanduser().read_text())
    if not isinstance(value, dict):
        raise ValueError("Harness config must be a JSON object")
    allowed = {"codex_command", "codex_source", "pi_source", "pi_command", "node_command",
               "responses_base_url", "responses_base_url_env", "allow_http", "api_key_env", "auth", "timeout_seconds",
               "request_timeout_seconds", "startup_timeout_seconds", "context_window", "reasoning_effort",
               "pi_profile", "pi_adaptive"}
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"Unknown harness settings: {sorted(unknown)}; use api_key_env for credentials")
    if "allow_http" in value and not isinstance(value["allow_http"], bool):
        raise ValueError("allow_http must be a boolean")
    if value.get("auth", "azure") not in {"azure", "bearer"}:
        raise ValueError("auth must be 'azure' or 'bearer'")
    if value.get("responses_base_url") is not None:
        validate_base_url(value["responses_base_url"], field="responses_base_url")
    for key in ("timeout_seconds", "request_timeout_seconds", "startup_timeout_seconds", "context_window"):
        if key in value and (isinstance(value[key], bool) or not isinstance(value[key], (int, float))
                             or not math.isfinite(value[key]) or value[key] <= 0):
            raise ValueError(f"{key} must be positive and finite")
    resolve_profile(value)
    return value


def native_connection(config: dict[str, Any]) -> tuple[str, str]:
    """Resolve a live gateway and its credential; synthetic checks do not call this."""
    url = configured_base_url(config, "responses_base_url")
    if not url:
        raise ValueError("Live native runs require an explicit responses_base_url or responses_base_url_env")
    url = validate_base_url(url, field="responses_base_url", allow_http=config.get("allow_http") is True)
    if config.get("auth", "azure") not in {"azure", "bearer"}:
        raise ValueError("auth must be 'azure' or 'bearer'")
    key_env = config.get("api_key_env", "AZURE_OPENAI_API_KEY")
    credential = os.environ.get(key_env)
    if not credential:
        raise ValueError(f"Missing credential environment variable: {key_env}")
    return url, credential


def native_command(harness: str, config: dict[str, Any]) -> list[str]:
    """Resolve an installed executable or the local Pi source launcher."""
    if harness == "codex":
        command = config.get("codex_command", ["codex", "app-server"])
    elif adaptive_enabled(config):
        package_identity()
        command = [config.get("node_command", "node"), "--experimental-strip-types",
                   str(PI_ADAPTIVE_PACKAGE / "src" / "runner.ts")]
    elif config.get("pi_command"):
        command = config["pi_command"]
    elif config.get("pi_source"):
        source = Path(config["pi_source"]).expanduser().resolve()
        resolver = source / "packages/coding-agent/src/experimental/source-resolver.ts"
        cli = source / "packages/coding-agent/src/cli.ts"
        if not resolver.is_file() or not cli.is_file():
            raise ValueError("pi_source must contain the Pi source CLI and source resolver")
        command = [config.get("node_command", "node"), "--import", resolver.as_uri(), str(cli)]
    else:
        command = ["pi"]
    if not isinstance(command, list) or not command or any(not isinstance(v, str) for v in command):
        raise ValueError("Native command must be a nonempty JSON string array")
    executable = shutil.which(command[0])
    if executable is None:
        raise FileNotFoundError(f"Native harness executable not found: {command[0]}")
    return [str(Path(executable).resolve()), *command[1:]]


def runtime_identity(harness: str, config: dict[str, Any]) -> dict[str, Any]:
    """Fingerprint the executing binary and independently identify source data."""
    command = native_command(harness, config)
    result: dict[str, Any] = {"command": command, "executable_sha256":
        hashlib.sha256(Path(command[0]).read_bytes()).hexdigest()}
    if harness == "pi" and adaptive_enabled(config):
        result.update(package_identity())
        return result
    source = config.get(f"{harness}_source")
    if source:
        try:
            result["source_commit"] = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=source, text=True, timeout=5,
                stderr=subprocess.DEVNULL).strip()
            diff = subprocess.check_output(["git", "diff", "HEAD"], cwd=source, timeout=5)
            result["source_diff_sha256"] = hashlib.sha256(diff).hexdigest()
            if harness == "pi":
                # Model data is generated and git-ignored; include it in runtime identity.
                files = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in sorted((Path(source) / "packages/ai/src/providers/data").glob("*.json"))}
                result["model_catalog_sha256"] = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
                result["version"] = json.loads((Path(source) / "packages/coding-agent/package.json").read_text())["version"]
        except (OSError, subprocess.SubprocessError):
            result["source_identity_error"] = True
    if harness == "codex":
        result["version"] = subprocess.check_output([command[0], "--version"], text=True,
            timeout=max(10, float(config.get("startup_timeout_seconds", 10)))).strip()
    return result


def child_environment(home: Path) -> dict[str, str]:
    # Allowlist, not a growing blacklist of providers' secret variable names.
    """Pass system essentials and an isolated home, excluding inherited secrets."""
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT", "LD_LIBRARY_PATH") if key in os.environ}
    env.update(HOME=str(home), NO_COLOR="1", TERM="dumb")
    return env


class JsonProcess:
    """Own a native JSONL process with concurrent event and stderr readers."""
    def __init__(self, command: list[str], cwd: Path, env: dict[str, str], events: NativeEvents):
        """Store runtime dependencies and initialize the native session boundary."""
        self.events = events
        self.process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
            bufsize=1, start_new_session=True)
        self.incoming: queue.Queue = queue.Queue()
        self.stderr = deque(maxlen=30)
        self.threads = []
        for stream, kind in ((self.process.stdout, "stdout"), (self.process.stderr, "stderr")):
            thread = threading.Thread(target=self._read, args=(stream, kind), daemon=True)
            thread.start()
            self.threads.append(thread)

    def _read(self, stream, kind):
        """Capture native stdout immediately while the main thread runs physics."""
        for line in stream:
            line = line.rstrip("\n")
            if kind == "stdout":
                try:
                    row = json.loads(line)
                except ValueError:
                    row = None
                if isinstance(row, dict):
                    try:
                        self.events.context.copy().run(self.events.consume, row)
                        self.incoming.put(("event", row))
                        continue
                    except Exception as exc:
                        self.incoming.put(("reader_error", exc))
                        return
            self.incoming.put((kind, line))

    def send(self, value):
        """Record and deliver one native control-protocol command."""
        event("native.command", kind="native", name=self.events.harness, data=value)
        self.process.stdin.write(json.dumps(value) + "\n")
        self.process.stdin.flush()

    def poll(self, bridge: EnvironmentBridge, deadline: float):
        """Pump owner-thread actions and return the next native protocol event."""
        bridge.drain()
        if time.monotonic() >= deadline:
            raise TimeoutError("Native harness episode timeout")
        try:
            kind, line = self.incoming.get(timeout=0.05)
        except queue.Empty:
            if self.process.poll() is not None:
                raise RuntimeError(f"Native process exited ({self.process.returncode}): " + "\n".join(self.stderr))
            return None
        if kind == "stderr":
            self.stderr.append(line)
            event("native.stderr", kind="native", name=self.events.harness, data={"text": line})
            return None
        if kind == "reader_error":
            raise RuntimeError("Native event recording failed") from line
        if kind != "event":
            event("native.stdout", kind="native", name=self.events.harness, data={"text": line})
            return None
        return line

    def close(self):
        """Terminate the native process group and close its pipes and readers."""
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=3)
        for thread in self.threads:
            thread.join(timeout=1)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            stream.close()


class NativeHarness:
    """Drive a persistent Codex or Pi session against shared local services."""
    def __init__(self, harness: str, config: dict[str, Any], model_config: dict[str, Any]):
        """Store runtime dependencies and initialize the native session boundary."""
        if harness not in EXTERNAL_HARNESSES:
            raise ValueError("Expected codex or pi")
        self.harness, self.config = harness, config
        self.model_config = resolved_model_settings(model_config)
        self.pi_profile = resolve_profile(config, self.model_config) if harness == "pi" else None
        if harness != "pi" and adaptive_enabled(config):
            raise ValueError("pi_profile=adaptive-v1 requires --harness pi")

    def run(self, bridge: EnvironmentBridge, output_dir: Path, *, responder=None, environment_binding=None, adaptive_setup=None):
        """Create an isolated session and drive it to completion or a recorded error."""
        deadline = time.monotonic() + float(self.config.get("timeout_seconds", 3600))
        if isinstance(bridge, dict):
            from .adaptive.bootstrap import BootstrapBridge
            if not self.pi_profile:
                raise ValueError("Minimal bootstrap requires the Pi adaptive profile")
            bridge = BootstrapBridge(bridge)
        identity = runtime_identity(self.harness, self.config)
        recorder = get_recorder()
        if recorder is not None:
            directory = recorder.directory / "native"
        else:
            import uuid
            directory = output_dir / "native_sessions" / uuid.uuid4().hex
        directory = directory.resolve()
        directory.mkdir(parents=True)
        if self.pi_profile:
            from .adaptive.service import AdaptiveService
            bridge = AdaptiveService(bridge, directory / "adaptive", deadline, binding=environment_binding)
            if adaptive_setup:
                adaptive_setup(bridge)
        home, workspace = directory / "home", directory / "workspace"
        home.mkdir()
        workspace.mkdir()
        url = self.config.get("responses_base_url")
        if responder is None:
            url, credential = native_connection(self.config)
        else:
            credential = None
        with span("harness.session", input={"harness": self.harness}, attributes={
            "identity": identity, "config": {**self.config, "responses_base_url": url}, "synthetic": responder is not None,
            "isolation": "separate_home_and_cwd; not an OS security boundary",
        }) as session:
            with LocalServices(bridge, upstream_url=str(url).rstrip("/") + "/responses" if url else None,
                               api_key=credential, azure=self.config.get("auth", "azure") == "azure",
                               timeout=float(self.config.get("request_timeout_seconds", 600)),
                               responder=responder, harness=self.harness, model_options=self.model_config,
                               pi_profile=self.pi_profile, deadline=deadline) as services:
                if self.pi_profile:
                    bridge.connect_reviewer(services)
                env = child_environment(home)
                command = native_command(self.harness, self.config)
                if self.harness == "codex":
                    self._codex_config(home, services, env)
                else:
                    self._pi_config(home, services, env)
                    if self.pi_profile:
                        runner_config = directory / "pi-adaptive.json"
                        runner_config.write_text(json.dumps({"profile": self.pi_profile,
                            "agent_dir": str(home / ".pi" / "agent"), "session_dir": str(directory / "sessions"),
                            "model": self.model_config["model"], "max_actions": bridge.max_steps,
                            "instruction": bridge.instruction, "connection": "environment"}))
                        env["PI_ADAPTIVE_CONFIG"] = str(runner_config)
                    else:
                        command += ["--mode", "rpc", "--provider", "humanclaw", "--model", self.model_config["model"],
                                    "--session-dir", str(directory / "sessions"),
                                    "--thinking", self.config.get("reasoning_effort", "medium")]
                events = NativeEvents(self.harness, services.call_names, services.requested_calls)
                process = JsonProcess(command, workspace, env, events)
                try:
                    if self.harness == "codex":
                        self._codex(process, services, bridge, deadline)
                    else:
                        self._wait_for_tools(process, services, bridge, deadline)
                        self._pi(process, bridge, deadline)
                    if not bridge.done:
                        bridge.done = True
                        bridge.termination = "agent_completed"
                    if services.calls == 0:
                        raise RuntimeError("Native harness made no observable model requests")
                    if not services.tools_listed.is_set():
                        raise RuntimeError("Native harness did not discover environment tools")
                    result = {"harness": self.harness, "native_directory": str(directory), "identity": identity,
                              "model_requests": services.calls, "steps": bridge.step,
                              "raw_model_usage": services.usage,
                              "termination_reason": bridge.termination,
                              "tools_exposed": sorted(services.exposed), "synthetic": responder is not None}
                    if self.pi_profile and bridge.adapters:
                        result["interface"] = bridge.adapters.report()
                    session.set_output(result)
                    return result
                finally:
                    if self.pi_profile and bridge.adapters:
                        from humanclaw_bench.experiments.report import normalize_model_usage
                        # Failed attempts retain usage and interface evidence too.
                        (directory / "interface-trial.json").write_text(json.dumps({
                            **bridge.adapters.report(), "model_requests": services.calls, "raw_model_usage": services.usage,
                            "usage_coverage": {"requests": services.calls, "with_usage": sum(
                                normalize_model_usage(row)["total_tokens"] is not None for row in services.usage)},
                            "runtime_identity": identity, "synthetic": responder is not None}, indent=2))
                    bridge.close()
                    process.close()
                    events.close()

    def _codex_config(self, home, services, env):
        """Configure Codex to use only the observed local model and MCP transports."""
        codex_home = home / ".codex"
        codex_home.mkdir()
        env.update(CODEX_HOME=str(codex_home), HUMANCLAW_PROXY_KEY=services.bearer)
        quote = json.dumps
        config = (
            f'model = {quote(self.model_config["model"])}\n'
            'model_provider = "humanclaw"\napproval_policy = "never"\nsandbox_mode = "workspace-write"\n'
            f'model_reasoning_effort = {quote(self.config.get("reasoning_effort", "medium"))}\n'
            f'model_context_window = {int(self.config.get("context_window", 131072))}\n'
            '[sandbox_workspace_write]\nnetwork_access = true\n'
            '[model_providers.humanclaw]\nname = "HumanCLAW observed Responses"\n'
            f'base_url = {quote(services.url + "/v1")}\n'
            'env_key = "HUMANCLAW_PROXY_KEY"\nwire_api = "responses"\nrequires_openai_auth = false\n'
            'supports_websockets = false\n'
            '[mcp_servers.humanclaw]\n'
            f'url = {quote(services.url + "/mcp")}\nrequired = true\n'
            f'startup_timeout_sec = {float(self.config.get("startup_timeout_seconds", 30)):g}\n'
            'tool_timeout_sec = 1200\n'
            f'http_headers = {{ Authorization = {quote("Bearer " + services.bearer)} }}\n'
        )
        (codex_home / "config.toml").write_text(config)

    def _pi_config(self, home, services, env):
        """Configure Pi models and direct MCP tools in a fresh agent directory."""
        agent = home / ".pi" / "agent"
        agent.mkdir(parents=True)
        env["PI_CODING_AGENT_DIR"] = str(agent)
        model = {"id": self.model_config["model"], "input": ["text", "image"], "reasoning": True,
                 "contextWindow": int(self.config.get("context_window", 131072)),
                 "maxTokens": int(self.model_config.get("max_tokens", 8192))}
        if self.pi_profile:
            # Disable unspecified labels; a model's provider mapping is explicit, never inferred from its name.
            model["thinkingLevelMap"] = {**dict.fromkeys(("off", "minimal", "low", "medium", "high", "xhigh", "max")),
                                         **self.pi_profile["model_capabilities"]["effort_map"]}
            # Transport cooldown covers HTTP and SSE throttles; the SDK owns turn retries.
            (agent / "settings.json").write_text(json.dumps({"httpIdleTimeoutMs": int(self.config.get("request_timeout_seconds", 600) * 1000),
                "retry": {"provider": {"maxRetries": 0}}}))
        (agent / "models.json").write_text(json.dumps({"providers": {"humanclaw": {
            "api": "openai-responses", "baseUrl": services.url + "/v1", "apiKey": services.bearer,
            "models": [model]}}}))
        (agent / "mcp.json").write_text(json.dumps({"mcpServers": {("environment" if self.pi_profile else "humanclaw"): {
            "url": services.url + "/mcp", "headers": {"Authorization": "Bearer " + services.bearer},
            "exposure": "direct", "timeout": 1200000}}}))

    def _codex(self, process, services, bridge, deadline):
        """Initialize App Server, start one thread and wait for turn completion."""
        counter = 0

        def request(method, params):
            """Match an App Server request ID while retaining intervening notifications."""
            nonlocal counter
            counter += 1
            ident = counter
            process.send({"id": ident, "method": method, "params": params})
            while True:
                row = process.poll(bridge, deadline)
                if row is not None and row.get("id") == ident:
                    if row.get("error"):
                        raise RuntimeError(f"Codex {method}: {row['error']}")
                    return row.get("result", {})

        request("initialize", {"clientInfo": {"name": "humanclaw-bench", "version": "0.1.0"}})
        process.send({"method": "initialized", "params": {}})
        thread = request("thread/start", {"model": self.model_config["model"], "modelProvider": "humanclaw",
                         "approvalPolicy": "never", "sandbox": "workspace-write"})
        thread_id = thread["thread"]["id"]
        self._wait_for_tools(process, services, bridge, deadline)
        pictures = bridge.initial_images() if hasattr(bridge, "initial_images") else [image_content(bridge.image)]
        request("turn/start", {"threadId": thread_id, "input": [
            {"type": "text", "text": bridge.initial_prompt()},
            *[{"type": "image", "url": f"data:{picture['mimeType']};base64,{picture['data']}"} for picture in pictures],
        ]})
        while True:
            row = process.poll(bridge, deadline)
            if row is None:
                continue
            if row.get("method") == "turn/completed":
                turn = row.get("params", {}).get("turn", {})
                if turn.get("status") != "completed":
                    raise RuntimeError(f"Codex turn failed: {turn.get('error') or turn.get('status')}")
                return

            if "id" in row and "method" in row:
                process.send({"id": row["id"], "error": {"code": -32601, "message": "Interactive requests unavailable in benchmark"}})
                raise RuntimeError("Codex requested interactive input during autonomous evaluation")

    def _wait_for_tools(self, process, services, bridge, deadline):
        """Require environment discovery before sending a task to the model."""
        timeout = float(self.config.get("startup_timeout_seconds", 30))
        with span("harness.environment_discovery", input={"timeout_seconds": timeout}):
            startup_deadline = min(deadline, time.monotonic() + timeout)
            while not services.tools_listed.is_set():
                try:
                    process.poll(bridge, startup_deadline)
                except TimeoutError as exc:
                    if time.monotonic() >= deadline:
                        raise
                    raise TimeoutError(
                        f"{self.harness} environment-tool discovery timed out after {timeout:g}s"
                    ) from exc

    def _pi(self, process, bridge, deadline):
        """Start a Pi RPC prompt and wait past retries for agent_settled."""
        process.send({"id": "episode", "type": "prompt", "message": bridge.initial_prompt(),
                      "images": bridge.initial_images() if hasattr(bridge, "initial_images") else [image_content(bridge.image)]})
        failed_message = None
        while True:
            row = process.poll(bridge, deadline)
            if row is None:
                continue
            if row.get("type") == "response" and row.get("success") is False:
                raise RuntimeError(f"Pi rejected request: {row.get('error')}")
            if row.get("type") == "message_end":
                message = row.get("message", {})
                if message.get("role") == "assistant":
                    failed_message = message.get("errorMessage") if message.get("stopReason") in {"error", "aborted"} else None
            if row.get("type") == "agent_settled":
                if row.get("aborted") or failed_message:
                    raise RuntimeError(f"Pi episode failed: {failed_message or 'aborted'}")
                return


def native_paper_cost(raw_usage, steps):
    """Populate legacy paper columns from the same authoritative HTTP usage."""
    from humanclaw_bench.experiments.report import normalize_model_usage
    normalized = [normalize_model_usage(value) for value in raw_usage]
    fields = ("input_tokens", "visible_output_tokens", "reasoning_tokens", "cached_input_tokens", "total_tokens")
    totals = {field: (sum(row[field] for row in normalized)
                      if normalized and all(row[field] is not None for row in normalized) else None)
              for field in fields}
    return {"decision_steps": steps, "vlm_calls": len(raw_usage),
            "token_source": "provider_exact" if all(value is not None for value in totals.values()) else "provider_partial",
            **totals, "input_tokens_per_step": totals["input_tokens"] / max(1, steps) if totals["input_tokens"] is not None else None,
            "visible_output_tokens_per_step": totals["visible_output_tokens"] / max(1, steps)
            if totals["visible_output_tokens"] is not None else None}
