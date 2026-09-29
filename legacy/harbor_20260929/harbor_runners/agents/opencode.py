"""The single production harness binding; no provider credentials enter the agent."""
import json

from harbor_runners.endpoints import validate_connection


def bind(connection, *, url, token):
    validate_connection(connection)
    provider = connection["provider_id"]
    settings = {"options": {"baseURL": url.rstrip("/") + "/v1", "apiKey": token},
                "models": {connection["model_id"]: {}}}
    if connection["npm"]:
        settings["npm"] = connection["npm"]
    overlay = {"provider": {provider: settings}, "enabled_providers": [provider],
               "model": connection["full_model_name"], "small_model": connection["full_model_name"],
               "autoupdate": False, "share": "disabled"}
    # Inline config takes precedence over workspace/global config. Only the
    # trial token and loopback URL appear here, never the real upstream key.
    env = {"OPENCODE_CONFIG_CONTENT": json.dumps(overlay),
           "OPENCODE_DISABLE_MODELS_FETCH": "true", "OPENCODE_DISABLE_AUTOUPDATE": "true"}
    return env, {"version": connection["opencode_version"], "opencode_config": overlay}


def create_delegate(connection, constructor, *, url, token):
    from harbor.agents.installed.opencode import OpenCode

    class IsolatedOpenCode(OpenCode):
        def _env_sources(self):
            return (self._resolved_env_vars, self._extra_env)

    env, options = bind(connection, url=url, token=token)
    args = dict(constructor)
    args.pop("extra_env", None)
    args["model_name"] = connection["full_model_name"]
    return IsolatedOpenCode(**args, extra_env=env, **options)
