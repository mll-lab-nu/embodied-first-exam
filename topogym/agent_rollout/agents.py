"""Replaceable coding-agent transports. Never pass a simulator handle to one."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

from topogym.agent_bridge.session import write_json

SCHEMA = dict(type="object", additionalProperties=False,
    properties=dict(kind=dict(type="string", enum=["segment", "inspect", "stop"]),
                    code=dict(type="string"), paths=dict(type="array", items=dict(type="string")),
                    reason=dict(type="string")), required=["kind", "code", "paths", "reason"])


def validate_decision(value):
    if not isinstance(value, dict) or value.get("kind") not in ("segment", "inspect", "stop"):
        raise ValueError("Expected a segment, inspect or stop decision")
    if value["kind"] == "segment" and not isinstance(value.get("code"), str):
        raise ValueError("segment needs Python code")
    if value["kind"] == "inspect" and (not isinstance(value.get("paths"), list) or
            not 1 <= len(value["paths"]) <= 16 or any(not isinstance(p, str) for p in value["paths"])):
        raise ValueError("inspect needs 1..16 relative PNG/JSON paths")
    return value


class ReplayAgent:
    """Deterministic transport smoke test, explicitly not a model evaluation."""
    isolation = "no_model"

    def __init__(self, config, public, private):
        self.config, self.public, self.private = config, Path(public), Path(private)
        self.decisions = iter(config.get("decisions", []))

    def decide(self, request, number):
        if self.config.get("tool_script") and number == 1:
            # Operator-authored deterministic SDK smoke program, never a model.
            script = self.public / "scratch" / "replay.py"
            script.write_text(self.config["tool_script"])
            result = subprocess.run(["/usr/bin/python3", str(script)], cwd=self.public,
                env=dict(os.environ, PYTHONPATH=str(self.public),
                    TOPOGYM_ENV_URL=self.config["environment_url"], TOPOGYM_ENV_TOKEN=self.config["environment_token"]),
                capture_output=True, text=True, timeout=self.config.get("timeout_s", 600))
            (self.private / "replay.stdout.txt").write_text(result.stdout)
            (self.private / "replay.stderr.txt").write_text(result.stderr)
            if result.returncode:
                raise RuntimeError("Replay SDK program failed; see private replay.stderr.txt")
        return next(self.decisions, dict(kind="stop", reason="Replay exhausted")), None


class CommandAgent:
    """One JSON request on stdin -> one JSON decision on stdout.

    The process receives only public paths in its request. A deployment may
    provide a container launcher here; a local cwd is NOT a read boundary.
    """
    isolation = "prompt_policy"

    def __init__(self, config, public, private):
        self.config, self.public, self.private = config, Path(public), Path(private)
        if not isinstance(config["command"], list) or not config["command"]:
            raise ValueError("command must be an argv list")

    def decide(self, request, number):
        env = dict(os.environ)
        if self.config.get("interaction") == "tools":
            env.update(TOPOGYM_ENV_URL=self.config["environment_url"], TOPOGYM_ENV_TOKEN=self.config["environment_token"],
                       PYTHONPATH=str(self.public))
        result = subprocess.run(self.config["command"], input=json.dumps(request), text=True,
            cwd=self.public, env=env, capture_output=True, timeout=self.config.get("timeout_s", 300))
        (self.private / f"call_{number}.stderr.txt").write_text(result.stderr)
        (self.private / f"call_{number}.stdout.txt").write_text(result.stdout)
        if result.returncode:
            raise RuntimeError(f"Agent command exited {result.returncode}; see private call log")
        response = json.loads(result.stdout)
        return response.get("decision", response), response.get("usage")


class CodexAgent:
    """codex exec JSONL transport, with one fresh thread per repeat.

    Each repeat has a fresh filesystem-visible Codex home. Only its RGB input
    workspace, scratch folder and generic system binaries are mounted.
    """
    isolation = "bwrap_mount_namespace"

    def __init__(self, config, public, private):
        self.config, self.public, self.private = config, Path(public), Path(private)
        self.thread = None
        self.budget, self.proxy = None, None
        self.temporary = tempfile.TemporaryDirectory(prefix="topogym-codex-")
        self.agent_home = Path(self.temporary.name) / "home"
        self.output = Path(self.temporary.name) / "output"
        self.agent_home.mkdir()
        self.output.mkdir()
        if not config.get("model"):
            raise ValueError("Select the Codex model explicitly")
        # Codex's nested workspace sandbox protects these directories with
        # mounts. Create empty mountpoints before the outer read-only bind.
        for name in (".git", ".codex", ".agents"):
            (self.public / name).mkdir(exist_ok=True)
        write_json(self.public / "decision_schema.json", SCHEMA)
        if config.get("token_limit", 0):
            from .budget_proxy import BudgetProxy
            from .token_budget import TokenBudget
            self.budget = TokenBudget(self.private, self.public, config["token_limit"])
            try:
                self.proxy = BudgetProxy(os.environ.get("CODEX_API_KEY") or os.environ.get("OPENAI_API_KEY"),
                    config["model"], self.budget, max_output_tokens=config.get("max_output_tokens", 8192),
                    timeout_s=config.get("timeout_s", 600))
            except Exception:
                self.temporary.cleanup()
                raise

    def decide(self, request, number):
        usage_start = len(self.budget.calls) if self.budget else 0
        if self.budget:
            self.budget.require_ready()
        response = self.output / f"call_{number}.response.json"
        args = [self.config.get("executable", "codex"), "exec"]
        if self.thread:
            args += ["resume"]
        else:
            args += ["--sandbox", "workspace-write", "-c", 'approval_policy="never"']
        args += ["--skip-git-repo-check", "--ignore-user-config", "--json", "--model", self.config["model"],
                 "--output-schema", "/workspace/decision_schema.json",
                 "--output-last-message", "/agent-output/" + response.name]
        if self.config.get("interaction") == "tools":
            args += ["-c", "sandbox_workspace_write.network_access=true"]
        if self.proxy:
            settings = {
                "model_provider": "topogym_metered",
                "model_providers.topogym_metered": dict(name="TopoGym budget proxy", base_url=self.proxy.base_url,
                    env_key="TOPOGYM_PROXY_TOKEN", wire_api="responses", requires_openai_auth=False,
                    supports_websockets=False, request_max_retries=0, stream_max_retries=0),
                "features.enable_request_compression": False,
                "features.multi_agent": False,
                "web_search": "disabled",
            }
            # Config table values need TOML syntax (not JSON object syntax).
            provider = settings.pop("model_providers.topogym_metered")
            settings.update({"model_providers.topogym_metered."+k: v for k, v in provider.items()})
            for key, value in settings.items():
                args += ["-c", key + "=" + json.dumps(value)]
        for path in request["images"]:
            args += ["--image", "/workspace/" + path]
        args += ([self.thread] if self.thread else []) + ["-"]
        from .isolation import sandbox_command
        args, env = sandbox_command(args, self.public, self.agent_home, self.output, inherit_auth=not bool(self.proxy))
        if self.config.get("interaction") == "tools":
            env.update(TOPOGYM_ENV_URL=self.config["environment_url"], TOPOGYM_ENV_TOKEN=self.config["environment_token"],
                       PYTHONPATH="/workspace")
        if self.proxy:
            env["TOPOGYM_PROXY_TOKEN"] = self.proxy.token
            for key in ("NO_PROXY", "no_proxy"):
                env[key] = "127.0.0.1,localhost" + (","+env[key] if env.get(key) else "")
        try:
            result = subprocess.run(args, input=request["prompt"], text=True, env=env,
                capture_output=True, timeout=self.config.get("timeout_s", 600))
        except subprocess.TimeoutExpired as exc:
            for suffix, value in (("events.jsonl", exc.stdout), ("stderr.txt", exc.stderr)):
                if isinstance(value, bytes):
                    value = value.decode(errors="replace")
                (self.private / f"call_{number}.{suffix}").write_text(value or "")
            if self.budget:
                self.budget.stop("provider_timeout", "Codex call timed out; no automatic retry")
            raise
        (self.private / f"call_{number}.events.jsonl").write_text(result.stdout)
        (self.private / f"call_{number}.stderr.txt").write_text(result.stderr)
        if self.budget:
            self.budget.require_ready()  # Surface upstream/budget errors, including unknown usage.
        if result.returncode:
            detail = result.stderr.strip()[-1000:]
            for line in reversed(result.stdout.splitlines()):
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("type") == "turn.failed":
                    detail = str(event.get("error", {}).get("message", detail))
                    break
            raise RuntimeError(f"Codex exited {result.returncode}: {detail}; see private call log")
        usage = None
        for line in result.stdout.splitlines():
            event = json.loads(line)
            if event.get("type") == "thread.started":
                self.thread = event["thread_id"]
            if event.get("type") == "turn.completed":
                usage = event.get("usage")
            if event.get("type") in ("turn.failed", "error"):
                raise RuntimeError("Codex turn failed; see private call log")
        if not self.thread or not response.is_file():
            raise RuntimeError("Codex did not return a thread and structured response")
        decision = json.loads(response.read_text())
        write_json(self.private / response.name, decision)
        if self.budget:
            usage = self.budget.usage_since(usage_start)
            if usage is None:
                raise RuntimeError("Codex returned a decision without metered request receipts")
        return decision, usage

    def close(self):
        if self.proxy:
            self.proxy.close()
        self.temporary.cleanup()


def create_agent(config, public, private):
    providers = dict(replay=ReplayAgent, command=CommandAgent, codex=CodexAgent)
    return providers[config["provider"]](config, public, private)
