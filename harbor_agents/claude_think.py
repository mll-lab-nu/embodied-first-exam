"""Claude Code (Harbor's claude-code agent) for interactive-mode tasks.

With `RCB_THINK_PROXY_URL` set (e.g. http://sim:18090), Claude Code talks to the task sidecar's
scripts/interactive/think_proxy.py instead of api.anthropic.com. The proxy holds the real subscription token
(the sidecar's CLAUDE_CODE_OAUTH_TOKEN, passed by docker compose) and meters every response's tokens for the
game clock; the agent container receives only a placeholder token, so it cannot reach the model around the meter.
Without the variable this behaves exactly like Harbor's claude-code agent.

    RCB_THINK_PROXY_URL=http://sim:18090 harbor run -p tasks/<task> \\
        -a harbor_agents.claude_think:ClaudeThink -m anthropic/claude-opus-5-5 --env-file .env -k 1 -n 1
"""
from __future__ import annotations

import os

from harbor.agents.installed.claude_code import ClaudeCode

PLACEHOLDER_TOKEN = "sk-ant-oat01-rcb-think-proxy-placeholder-000000000000000000000000000000000000000000000000000"


def _think_url(override: str | None = None) -> str | None:
    url = (override or os.environ.get("RCB_THINK_PROXY_URL") or "").strip().rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]                 # Claude Code appends /v1/messages itself
    return url or None


class ClaudeThink(ClaudeCode):
    def __init__(self, *args, think_proxy_url: str | None = None, **kwargs):
        # think_proxy_url: this agent's metering proxy (a multi-seat task gives every seat its own);
        # default: RCB_THINK_PROXY_URL.
        self._think_proxy_url = think_proxy_url
        super().__init__(*args, **kwargs)

    def _resolve_auth_env(self) -> dict[str, str]:
        env = super()._resolve_auth_env()
        url = _think_url(self._think_proxy_url)
        if not url:
            return env
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("ANTHROPIC_AUTH_TOKEN", None)
        env["CLAUDE_CODE_OAUTH_TOKEN"] = PLACEHOLDER_TOKEN
        env["ANTHROPIC_BASE_URL"] = url
        return env
