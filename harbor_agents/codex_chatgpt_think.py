"""Codex on a ChatGPT subscription for interactive-mode tasks (metered, credential-isolated).

With `RCB_THINK_PROXY_URL` (e.g. http://sim:18090) the agent's Codex is logged in "with ChatGPT" through a
placeholder auth.json (scripts/interactive/fake_codex_auth.py: unsigned JWT-shaped tokens, placeholder account) and
talks to a custom provider at <url>/backend-api/codex with `requires_openai_auth`, so it sends ChatGPT-backend
requests to the sidecar's think_proxy. The proxy replaces the credentials with the sidecar's real CODEX_ACCESS_TOKEN /
CODEX_ACCOUNT_ID (from the bench .env, compose-interpolated), forwards to https://chatgpt.com and meters the tokens.

    RCB_THINK_PROXY_URL=http://sim:18090 PYTHONPATH=$PWD harbor run -p tasks/<task> \\
        -a harbor_agents.codex_chatgpt_think:CodexChatGPTThink -m openai/gpt-6-astra --env-file .env -k 1 -n 1
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from harbor.agents.installed.codex import Codex

HERE = Path(__file__).resolve().parent


def _think_url(override: str | None = None) -> str:
    url = (override or os.environ.get("RCB_THINK_PROXY_URL") or "").strip().rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]
    if not url:
        raise ValueError("CodexChatGPTThink needs RCB_THINK_PROXY_URL (the sidecar's think proxy, e.g. http://sim:18090)")
    return url


class CodexChatGPTThink(Codex):
    def __init__(self, *args, think_proxy_url: str | None = None, **kwargs):
        # think_proxy_url: this agent's metering proxy (a multi-seat task gives every seat its own);
        # default: RCB_THINK_PROXY_URL.
        self._think_proxy_url = think_proxy_url
        super().__init__(*args, **kwargs)

    def _resolve_auth_json_path(self) -> Path | None:
        path = Path(tempfile.mkdtemp(prefix="rcb-codex-auth-")) / "auth.json"
        subprocess.run([sys.executable, str(HERE.parent / "scripts" / "interactive" / "fake_codex_auth.py"), str(path)],
                       check=True, capture_output=True)
        return path

    def _build_effective_config(self, openai_base_url: str | None = None) -> dict[str, Any]:
        config = super()._build_effective_config(None)
        config.pop("openai_base_url", None)
        config["model_provider"] = "chatgpt_think"
        config.setdefault("model_providers", {})["chatgpt_think"] = {
            "name": "ChatGPT subscription via the think proxy",
            "base_url": f"{_think_url(self._think_proxy_url)}/backend-api/codex",
            "wire_api": "responses",
            "requires_openai_auth": True,
            "supports_websockets": False,
        }
        return config
