"""Run OpenRouter models with Harbor's native Codex CLI harness.

Harbor 0.23's Codex adapter treats the model prefix as metadata and passes only
the final slash-delimited component to ``codex --model``.  OpenRouter model IDs
themselves contain a slash (for example ``deepseek/deepseek-v4.1-flash``), so
this adapter preserves everything after Harbor's ``openrouter/`` prefix.

The parent adapter expects OpenAI-style runtime variables.  Selecting the
OpenRouter model connection here lets Harbor read ``OPENROUTER_API_KEY`` and
then safely translate it for the Codex subprocess without duplicating the key
in ``.env``.
"""

from __future__ import annotations

from dataclasses import replace
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


class CodexOpenRouter(Codex):
    """Codex harness connected to OpenRouter's OpenAI-compatible endpoint."""

    MODEL_CONNECTION = ModelConnectionSpec(default_provider="openrouter")

    @property
    def model_connection(self) -> ResolvedModelConnection:
        connection = super().model_connection
        # Harbor's Codex adapter applies only an explicitly configured URL, while
        # the shared resolver represents OpenRouter's standard URL as a default.
        # Promote that default so the generated custom provider receives it.
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
        providers["openrouter"] = {
            "name": "OpenRouter",
            "base_url": openai_base_url or "https://openrouter.ai/api/v1",
            "env_key": "OPENAI_API_KEY",
            "wire_api": "responses",
            "supports_websockets": False,
        }
        return config

    async def run(self, instruction, environment, context) -> None:
        if not self.model_name or not self.model_name.startswith("openrouter/"):
            raise ValueError(
                "CodexOpenRouter model must be openrouter/<provider>/<model>, "
                "for example openrouter/deepseek/deepseek-v4.1-flash"
            )

        original_model_name = self.model_name
        self.model_name = _OpenRouterModelName(original_model_name)
        try:
            await super().run(instruction, environment, context)
        finally:
            self.model_name = original_model_name
