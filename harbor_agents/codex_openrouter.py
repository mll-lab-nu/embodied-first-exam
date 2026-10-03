"""Run OpenRouter models with Harbor's native Codex CLI harness.

Harbor's Codex adapter treats the model prefix as metadata and passes only
the final slash-delimited component to ``codex --model``. OpenRouter model IDs
themselves use ``provider/model`` form, so this adapter preserves everything
after Harbor's ``openrouter/`` prefix.

The parent adapter expects OpenAI-style runtime variables.  Selecting the
OpenRouter model connection here lets Harbor read ``OPENROUTER_API_KEY`` and
then safely translate it for the Codex subprocess without duplicating the key
in ``.env``.
"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Any

from harbor.agents.installed.codex import Codex
from harbor.agents.model_connection import ModelConnectionSpec, ResolvedModelConnection


class _OpenRouterModelName(str):
    """Make Harbor's final-component split retain OpenRouter's nested ID."""

    def split(self, sep: str | None = None, maxsplit: int = -1) -> list[str]:
        if sep == "/" and maxsplit == -1:
            provider, separator, model_id = str(self).partition("/")
            if separator and provider == "openrouter" and model_id:
                return [provider, model_id]
        return super().split(sep, maxsplit)


# Providers whose Responses endpoint rejects a conversation that ends with a model turn
# (Google: 400 "Requests ending with a model turn are not supported."). Codex produces exactly
# that when it retries after a dropped stream, so for these we route through a local proxy
# (harbor_agents/or_proxy.py) that appends a user turn to such requests. Override with
# RCB_OR_PROXY=1 / RCB_OR_PROXY=0.
MODEL_TURN_SENSITIVE_PROVIDERS = {"google"}
PROXY_PORT = 18080
PROXY_REMOTE_PATH = "/tmp/or_proxy.py"

# Interactive mode ("thinking costs sim time"): RCB_THINK_PROXY_URL=<url>, e.g. http://127.0.0.1:18090/v1.
# Codex then talks to scripts/interactive/think_proxy.py in the task's sim sidecar, which holds the real
# OpenRouter key and meters every response's tokens for the game clock. The agent container receives only
# a placeholder key, so it cannot reach the model around the meter.
THINK_PLACEHOLDER_KEY = "rcb-think-proxy-placeholder"


def _think_url(override: str | None = None) -> str | None:
    url = (override or os.environ.get("RCB_THINK_PROXY_URL") or "").strip()
    return url or None


class CodexOpenRouter(Codex):
    """Codex harness connected to OpenRouter's OpenAI-compatible endpoint."""

    MODEL_CONNECTION = ModelConnectionSpec(default_provider="openrouter")

    def __init__(self, *args, think_proxy_url: str | None = None, **kwargs):
        # think_proxy_url: this agent's metering proxy (a multi-seat task gives every seat its own);
        # default: RCB_THINK_PROXY_URL.
        self._think_proxy_url = think_proxy_url
        super().__init__(*args, **kwargs)

    def _think(self) -> str | None:
        return _think_url(getattr(self, "_think_proxy_url", None))

    def _use_proxy(self) -> bool:
        flag = os.environ.get("RCB_OR_PROXY")
        if flag is not None:
            return flag.strip() not in ("", "0", "false", "no")
        nested = str(self.model_name or "").partition("/")[2]      # "<provider>/<model>"
        return nested.partition("/")[0] in MODEL_TURN_SENSITIVE_PROVIDERS

    @property
    def model_connection(self) -> ResolvedModelConnection:
        connection = super().model_connection
        # Harbor's Codex adapter applies only an explicitly configured URL, while
        # the shared resolver represents OpenRouter's standard URL as a default.
        # Promote that default so the generated custom provider receives it.
        if self._think():
            # the real key stays in the sidecar's think_proxy; the agent container gets a placeholder
            env = {k: v for k, v in connection.env.items() if not any(t in k.upper() for t in ("KEY", "TOKEN", "SECRET"))}
            return replace(connection, configured_base_url=self._think(), api_key=THINK_PLACEHOLDER_KEY, env=env)
        return replace(
            connection,
            configured_base_url=connection.configured_base_url or connection.base_url,
        )

    def _build_effective_config(
        self, openai_base_url: str | None = None
    ) -> dict[str, Any]:
        """Register OpenRouter explicitly so Codex stays on HTTPS Responses."""
        config = super()._build_effective_config()
        config.pop("openai_base_url", None)
        config["model_provider"] = "openrouter"

        providers = config.setdefault("model_providers", {})
        if not isinstance(providers, dict):
            raise ValueError("Codex config model_providers must be a TOML table")
        base_url = openai_base_url or "https://openrouter.ai/api/v1"
        if self._think():
            # Codex talks to the sidecar's metering proxy (which also applies the model-turn repair).
            base_url = self._think()
        elif self._use_proxy():
            # Codex talks to the local repair proxy, which forwards to OpenRouter.
            base_url = f"http://127.0.0.1:{PROXY_PORT}/v1"
        providers["openrouter"] = {
            "name": "OpenRouter",
            "base_url": base_url,
            "env_key": "OPENAI_API_KEY",
            "wire_api": "responses",
            "supports_websockets": False,
        }
        return config

    async def _start_proxy(self, environment) -> None:
        """Upload and start or_proxy.py inside the agent container (detached)."""
        await environment.upload_file(Path(__file__).with_name("or_proxy.py"), PROXY_REMOTE_PATH)
        await self.exec_as_agent(
            environment,
            command=(
                "mkdir -p /logs/agent\n"
                f"nohup python3 {PROXY_REMOTE_PATH} {PROXY_PORT} >/logs/agent/or_proxy.log 2>&1 &\n"
                "for i in 1 2 3 4 5 6 7 8 9 10; do\n"
                f"  (exec 3<>/dev/tcp/127.0.0.1/{PROXY_PORT}) 2>/dev/null && break; sleep 0.5\n"
                "done\n"
                "cat /logs/agent/or_proxy.log"
            ),
        )

    async def run(self, instruction, environment, context) -> None:
        prefix, separator, nested_model_id = str(self.model_name or "").partition("/")
        nested_provider, nested_separator, nested_model = nested_model_id.partition("/")
        if (
            not separator
            or prefix != "openrouter"
            or not nested_provider
            or not nested_separator
            or not nested_model
        ):
            raise ValueError(
                "CodexOpenRouter model must be openrouter/<provider>/<model>, "
                "for example openrouter/provider/model-name"
            )

        original_model_name = self.model_name
        self.model_name = _OpenRouterModelName(original_model_name)
        try:
            if self._use_proxy() and not self._think():
                await self._start_proxy(environment)
            await super().run(instruction, environment, context)
        finally:
            self.model_name = original_model_name
