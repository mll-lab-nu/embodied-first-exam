"""Run Codex on a ChatGPT login (the user's own Codex usage) with the client-side behaviour of our OpenRouter runs.

    PYTHONPATH=. harbor run -p tasks/<task> -a harbor_agents.codex_chatgpt:CodexChatGPT -m chatgpt/openai/gpt-6-luna \\
        --ak reasoning_effort=xhigh [--ak version=0.157.0]
    login: CODEX_AUTH_JSON_PATH=<auth.json>, default ~/.codex/auth.json (``codex login`` with ChatGPT)

Why not Harbor's own ``-a codex`` on the login: with ChatGPT auth and ``--model gpt-6-luna`` Codex applies the server's
metadata for that model ("Fast and affordable model for easier tasks", low verbosity, its own base instructions) and ends
its single turn within minutes. On 9 RoboWits task-mode pairs it scored 2/9 where the OpenRouter runs scored 7/9. Through
OpenRouter, Codex saw the nested id ``openai/gpt-6-luna``, found no metadata for it and used its generic fallback.

So this is CodexOpenRouter unchanged on the Codex side: the nested model id, the Responses provider without websockets,
the model gateway. Only the gateway's upstream differs: ChatGPT's Codex backend. The gateway holds the login's access
token, and never the refresh token, which stays on the host. It adds the account-id header, maps /v1/responses onto
<base>/responses and pins the served model name (``gpt-6-luna``). Every exchange is logged to ``agent/gateway.jsonl``
as before.

Effort: the ChatGPT backend spends far less reasoning at a given effort than the API.
- Measured on 2026-09-25 against the OpenRouter-flex runs at ``medium``: 448 reasoning tokens per call (median over 15
  trials), request latency median 8.6 s / mean 18.9 s.
- The same ``medium`` here gave 72 tokens per call, 3.5 s, and the agent gave up.
- ``high`` gave 305 tokens per call at 3.5 s / 7.7 s.
- ``xhigh`` gave 947-970 tokens per call at 7.3 s / 18.0 s, and kept working like the flex runs. Use ``xhigh`` to match
  the OpenRouter ``medium`` runs.
- The server also applies top_p 0.98 (the API applies 1.0).
- Details: jobs/journal/2026-09-25 (ab_diff.py, path_stats.py, replay_effort.py)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harbor.agents.model_connection import ModelConnectionSpec

from harbor_agents.codex_openrouter import CodexOpenRouter


class CodexChatGPT(CodexOpenRouter):
    """CodexOpenRouter's client setup, with the model gateway pointed at ChatGPT's Codex backend and a ChatGPT login."""

    MODEL_CONNECTION = ModelConnectionSpec(default_provider="chatgpt")
    MODEL_PREFIX = "chatgpt"
    GATEWAY_UPSTREAM = "https://chatgpt.com/backend-api/codex"
    PROVIDER_ID, PROVIDER_NAME = "chatgpt", "ChatGPT Codex backend (via the model gateway)"

    def _login(self) -> dict[str, str]:
        path = Path(self._get_env("CODEX_AUTH_JSON_PATH") or Path.home() / ".codex" / "auth.json").expanduser()
        tokens = (json.loads(path.read_text()).get("tokens") or {}) if path.is_file() else {}
        if not tokens.get("access_token") or not tokens.get("account_id"):
            raise RuntimeError(f"no ChatGPT login in {path}: run `codex login` (ChatGPT) or set CODEX_AUTH_JSON_PATH")
        return tokens

    def _gateway_key(self) -> str:
        return self._login()["access_token"]

    def _gateway_config(self) -> dict[str, Any]:
        return {"model": self._nested_model().split("/", 1)[-1],          # openai/gpt-6-luna -> gpt-6-luna
                "headers": {"chatgpt-account-id": self._login()["account_id"]},
                "strip_prefix": "/v1"}
