"""Small TopoGym adapters around Harbor's installed Codex agent.

Harbor owns installation, execution, token accounting and trajectory collection.
These adapters do not use the retired runner or a separate budget gateway.
"""
from pathlib import Path
import re
import shlex
from harbor.agents.installed.codex import Codex
from harbor.agents.model_connection import ModelConnectionSpec


class CodexOpenRouter(Codex):
    MODEL_CONNECTION = ModelConnectionSpec(default_provider="openrouter")

    def __init__(self,*args,**kwargs):
        kwargs.setdefault("web_search","disabled")
        super().__init__(*args,**kwargs)
        if not self.model_name or not re.fullmatch(r"openrouter/[A-Za-z0-9_.:/-]+",self.model_name):
            raise ValueError("Use openrouter/<provider>/<model> as the model name")

    def _build_effective_config(self,openai_base_url):
        config=super()._build_effective_config(openai_base_url)
        endpoint=openai_base_url or self.model_connection.base_url
        if not endpoint:
            raise ValueError("Set OPENROUTER_BASE_URL to the provider's Responses API base URL")
        config["model_provider"]="topogym_openrouter"
        config.setdefault("model_providers",{})["topogym_openrouter"] = dict(
            name="OpenRouter",base_url=endpoint,env_key="OPENAI_API_KEY",wire_api="responses")
        return config

    async def exec_as_agent(self,environment,command,**kwargs):
        # Harbor 0.23 formats --model with only the last slash component.
        # Rewrite that one generated CLI argument; preserve the full provider ID.
        if "codex exec " in command:
            model=self.model_name.removeprefix("openrouter/")
            command,count=re.subn(r"(?<=--model )[^\s]+",lambda _:shlex.quote(model),command,count=1)
            if count != 1:
                raise RuntimeError("Installed Harbor Codex command format changed")
        return await super().exec_as_agent(environment,command=command,**kwargs)


class CodexChatGPT(Codex):
    """Use Harbor's official auth.json injection with an explicit local login."""
    def __init__(self,*args,**kwargs):
        kwargs.setdefault("web_search","disabled")
        super().__init__(*args,**kwargs)

    def _resolve_auth_json_path(self):
        path=Path(self._get_env("CODEX_AUTH_JSON_PATH") or Path.home()/".codex/auth.json").expanduser()
        if not path.is_file():
            raise ValueError("Set CODEX_AUTH_JSON_PATH to an existing Codex login file")
        return path
