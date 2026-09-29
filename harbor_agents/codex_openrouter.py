"""Run OpenRouter models with Harbor's native Codex CLI harness.

    PYTHONPATH=. harbor run -p tasks/<task> -a harbor_agents.codex_openrouter:CodexOpenRouter \
        -m openrouter/<provider>/<model> --env-file .env [--ak reasoning_effort=medium] \
        [--ak provider_only=openai/flex] [--ak allow_fallbacks=false] [--ak web_search=live]

From Chi's adapter (dev/chi): Harbor 0.23's Codex adapter passes only the last slash-delimited component of the model id
to ``codex --model``, which would turn ``openrouter/openai/gpt-6-luna`` into ``gpt-6-luna``; this adapter keeps the nested
``<provider>/<model>`` id and registers OpenRouter as a Responses-API provider for Codex.
From Pingyue's (dev/pingyue): Codex sends a live ``web_search`` tool by default and OpenRouter runs it server-side, so
the traffic goes to the model-API host the agent must reach and no egress allowlist can stop it; it is off by default.
Ours: Codex talks to a small model gateway (``llm_gateway.py``) that this adapter starts inside the container on
127.0.0.1:8787. The gateway holds the OpenRouter key (Codex's own environment and auth file get a placeholder), pins the
model and OpenRouter's provider routing on every request (``provider_only`` / ``allow_fallbacks``, e.g. only
``openai/flex``, which the Codex CLI cannot set), retries OpenRouter's flex-tier throttling (which arrives as an HTTP 200
whose stream starts with an error event, and would otherwise end the session), and logs every exchange to
``agent/gateway.jsonl``."""

from __future__ import annotations

import json
import shlex
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import Field

from harbor.agents.installed.codex import Codex, CodexOptions
from harbor.agents.model_connection import ModelConnectionSpec, ResolvedModelConnection
from harbor.environments.base import BaseEnvironment
from harbor.models.trial.paths import EnvironmentPaths

GATEWAY_PORT = 8787
GATEWAY_DIR = PurePosixPath("/tmp/rcb-gateway")
GATEWAY_SOURCE = Path(__file__).with_name("llm_gateway.py")
PLACEHOLDER_KEY = "rcb-model-gateway"


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


class _OpenRouterModelName(str):
    """Make Harbor's final-component split retain the nested ID (openrouter/openai/gpt-6-luna -> openai/gpt-6-luna)."""

    def split(self, sep: str | None = None, maxsplit: int = -1) -> list[str]:
        if sep == "/" and maxsplit == -1:
            provider, separator, model_id = str(self).partition("/")
            if separator and "/" in model_id:
                return [provider, model_id]
        return super().split(sep, maxsplit)


class CodexOpenRouterOptions(CodexOptions):
    """Codex's options plus the gateway's (these two never become CLI flags)."""
    provider_only: str | None = Field(default=None, description="Comma-separated OpenRouter provider tags to route to, e.g. openai/flex.")
    allow_fallbacks: bool | None = Field(default=None, description="Allow other providers when provider_only fails; default false once it is set.")
    dump_requests: int | None = Field(default=None, description="Save the first N request bodies the gateway sends upstream (agent/requests/).")


class CodexOpenRouter(Codex):
    """Codex harness connected to OpenRouter's OpenAI-compatible Responses endpoint through the model gateway."""

    MODEL_CONNECTION = ModelConnectionSpec(default_provider="openrouter")
    options_model = CodexOpenRouterOptions
    MODEL_PREFIX = "openrouter"                    # -m <prefix>/<provider>/<model>
    GATEWAY_UPSTREAM = "https://openrouter.ai/api"
    PROVIDER_ID, PROVIDER_NAME = "openrouter", "OpenRouter"   # the Codex provider entry (base_url: the gateway)

    def __init__(self, *args: Any, provider_only: str | None = None, allow_fallbacks: Any = None,
                 dump_requests: Any = None, **kwargs: Any) -> None:
        kwargs.setdefault("web_search", "disabled")
        self._dump_requests = int(dump_requests or 0)
        self._provider = None
        if provider_only:
            only = [p.strip() for p in str(provider_only).split(",") if p.strip()]
            self._provider = {"only": only, "allow_fallbacks": False if allow_fallbacks is None else _as_bool(allow_fallbacks)}
        self._gateway_up = False
        super().__init__(*args, **kwargs)

    def _nested_model(self) -> str:
        prefix, sep, nested = str(self.model_name or "").partition("/")
        if prefix != self.MODEL_PREFIX or not sep or "/" not in nested:
            raise ValueError(f"{type(self).__name__} model must be {self.MODEL_PREFIX}/<provider>/<model>, "
                             f"for example {self.MODEL_PREFIX}/openai/gpt-6-luna")
        return nested

    @property
    def model_connection(self) -> ResolvedModelConnection:
        connection = super().model_connection
        if self._gateway_up:     # Codex itself only ever sees the gateway and a placeholder key
            return replace(connection, api_key=PLACEHOLDER_KEY, configured_base_url=f"http://127.0.0.1:{GATEWAY_PORT}/v1")
        # Harbor's Codex adapter applies only an explicitly configured URL; promote OpenRouter's default one.
        return replace(connection, configured_base_url=connection.configured_base_url or connection.base_url)

    def _build_effective_config(self, openai_base_url: str | None = None) -> dict[str, Any]:
        """Register OpenRouter explicitly so Codex stays on HTTPS Responses (here: the gateway in front of it)."""
        config = super()._build_effective_config()
        config.pop("openai_base_url", None)
        config["model_provider"] = self.PROVIDER_ID
        providers = config.setdefault("model_providers", {})
        if not isinstance(providers, dict):
            raise ValueError("Codex config model_providers must be a TOML table")
        providers[self.PROVIDER_ID] = {
            "name": self.PROVIDER_NAME,
            "base_url": openai_base_url or "https://openrouter.ai/api/v1",
            "env_key": "OPENAI_API_KEY",
            "wire_api": "responses",
            "supports_websockets": False,
        }
        return config

    def _resolve_auth_json_path(self):
        """Never hand a login to Codex in the container: the gateway holds the credential and Codex gets the placeholder
        key. Harbor's Codex would otherwise upload a whole auth.json (a ChatGPT login's refresh token included) whenever
        CODEX_AUTH_JSON_PATH or CODEX_FORCE_AUTH_JSON is set, and then leave OPENAI_API_KEY unset, so every trial fails
        with "Missing environment variable: OPENAI_API_KEY" (found on ws, 2026-09-25)."""
        return None

    def _gateway_key(self) -> str:
        """The credential the gateway sends upstream (Codex itself only gets a placeholder)."""
        key = super().model_connection.api_key or ""
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY is not set; pass it with --env-file")
        return key

    def _gateway_config(self) -> dict[str, Any]:
        config: dict[str, Any] = {"model": self._nested_model()}
        if self._provider:
            config["provider"] = self._provider
        return config

    async def _start_gateway(self, environment: BaseEnvironment) -> None:
        key, config = self._gateway_key(), self._gateway_config()
        if self._dump_requests:
            config["dump_requests"] = self._dump_requests
        logs = EnvironmentPaths.agent_dir.as_posix()
        await self.exec_as_agent(environment, command=f"mkdir -p {GATEWAY_DIR} {logs}")
        await self._upload_config_text(environment, content=GATEWAY_SOURCE.read_text(),
                                       remote_path=(GATEWAY_DIR / "llm_gateway.py").as_posix(), filename="llm_gateway.py")
        await self._upload_config_text(environment, content=key, remote_path=(GATEWAY_DIR / "key").as_posix(), filename="key")
        start = (f"(setsid nohup python3 {GATEWAY_DIR}/llm_gateway.py --port {GATEWAY_PORT} --key-file {GATEWAY_DIR}/key "
                 f"--upstream {shlex.quote(self.GATEWAY_UPSTREAM)} "
                 f"--log {logs}/gateway.jsonl --config {shlex.quote(json.dumps(config))} > {logs}/gateway.err 2>&1 < /dev/null &); "
                 f"for i in $(seq 1 100); do python3 -c \"import urllib.request; "
                 f"urllib.request.urlopen('http://127.0.0.1:{GATEWAY_PORT}/healthz', timeout=1)\" 2>/dev/null && exit 0; "
                 f"sleep 0.2; done; echo 'model gateway did not start' >&2; exit 1")
        await self.exec_as_agent(environment, command=start)
        self._gateway_up = True
        self.logger.info(f"{type(self).__name__}: model gateway up, upstream {self.GATEWAY_UPSTREAM}, model {config.get('model')}")

    async def run(self, instruction, environment, context) -> None:
        self._nested_model()
        await self._start_gateway(environment)
        original_model_name = self.model_name
        self.model_name = _OpenRouterModelName(original_model_name)
        try:
            await super().run(instruction, environment, context)
        finally:
            self.model_name = original_model_name
