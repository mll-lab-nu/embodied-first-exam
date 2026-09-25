"""Run OpenRouter models with Harbor's native Claude Code harness.

Harbor's Claude Code adapter talks to Anthropic: it sends the key as ``ANTHROPIC_API_KEY`` (an
``x-api-key`` header) and, without an explicit base URL, to api.anthropic.com. OpenRouter's
Anthropic-compatible endpoint wants ``ANTHROPIC_BASE_URL=https://openrouter.ai/api``, the key as
``ANTHROPIC_AUTH_TOKEN`` (a bearer token), and its own model ids (``anthropic/claude-opus-5.5``).
This adapter reads ``OPENROUTER_API_KEY`` and makes that translation, so the key is not duplicated
in ``.env``. Model names are ``openrouter/<provider>/<model>``, as for ``CodexOpenRouter``.
"""

from __future__ import annotations

from typing import Any

from harbor.agents.installed.claude_code import ClaudeCode
from harbor.agents.model_connection import ModelConnectionSpec

from harbor_agents.limited import end_trial

OPENROUTER_ANTHROPIC_URL = "https://openrouter.ai/api"  # Claude Code appends /v1/messages


class ClaudeCodeOpenRouter(ClaudeCode):
    """Claude Code harness connected to OpenRouter's Anthropic-compatible endpoint."""

    MODEL_CONNECTION = ModelConnectionSpec(default_provider="openrouter")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # WebSearch hands the query back to the model API with Anthropic's server-side search tool,
        # which OpenRouter runs: past the task's allowlist, the same leak as codex's web_search
        # (docs/LEAKAGE.md). WebFetch fetches from the container, so the allowlist would block it;
        # it is off so that no run depends on that. `--ak disallowed_tools=...` replaces this list.
        kwargs.setdefault("disallowed_tools", "WebSearch,WebFetch")
        super().__init__(*args, **kwargs)
        if not (self.model_name or "").startswith("openrouter/"):
            raise ValueError(
                "ClaudeCodeOpenRouter model must be openrouter/<provider>/<model>, "
                "for example openrouter/anthropic/claude-opus-5.5"
            )

    async def run(self, instruction, environment, context) -> None:
        try:
            await super().run(instruction, environment, context)
        finally:
            await end_trial(environment)

    def _resolved_model_name(self) -> str | None:
        return self.model_name.removeprefix("openrouter/") if self.model_name else None

    def _resolve_auth_env(self) -> dict[str, str]:
        key = self.model_connection.api_key
        if not key:
            raise ValueError("ClaudeCodeOpenRouter needs OPENROUTER_API_KEY")
        # No ANTHROPIC_API_KEY: OpenRouter authenticates the bearer token only.
        return {"ANTHROPIC_BASE_URL": OPENROUTER_ANTHROPIC_URL, "ANTHROPIC_AUTH_TOKEN": key}
