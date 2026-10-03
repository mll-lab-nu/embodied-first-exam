"""Codex using the trusted simulator's Azure Responses metering proxy.

The Azure key stays in the simulator sidecar. There is no provider fallback.
"""
from __future__ import annotations

import os
import re
from typing import Any

from harbor.agents.installed.codex import Codex
from harbor.agents.model_connection import ModelConnectionSpec, ResolvedModelConnection


class CodexAzureThink(Codex):
    MODEL_CONNECTION = ModelConnectionSpec(default_provider="azure")

    def _think_url(self) -> str:
        url = os.environ.get("RCB_THINK_PROXY_URL", "").strip()
        if not url:
            raise ValueError("RCB_THINK_PROXY_URL is required for metered Azure Codex")
        if os.environ.get("THINK_OPENAI_ROUTE", "").strip().lower() != "azure":
            raise ValueError("THINK_OPENAI_ROUTE must be azure; no fallback is allowed")
        return url

    @property
    def model_connection(self) -> ResolvedModelConnection:
        # Never resolve or transfer the real Azure credential into the agent.
        return ResolvedModelConnection(
            provider="azure", api_key="rcb-think-proxy-placeholder",
            base_url=self._think_url(), configured_base_url=self._think_url(),
        )

    def _resolve_auth_json_path(self):
        return None

    def _build_effective_config(self, openai_base_url=None) -> dict[str, Any]:
        config = super()._build_effective_config()
        config.pop("openai_base_url", None)
        config["model_provider"] = "azure"
        config["model_providers"] = {
            "azure": {
                "name": "Azure (simulator meter)",
                "base_url": self._think_url(),
                "env_key": "OPENAI_API_KEY",
                "wire_api": "responses",
                "supports_websockets": False,
            }
        }
        return config

    async def run(self, instruction, environment, context) -> None:
        if not re.fullmatch(r"azure/[A-Za-z0-9_.-]+", str(self.model_name or "")):
            raise ValueError("Expected azure/<deployment-name>")
        self._think_url()
        await super().run(instruction, environment, context)
