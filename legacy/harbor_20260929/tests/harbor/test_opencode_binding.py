import json
from pathlib import Path

import pytest

from harbor_runners.agents.opencode import bind, create_delegate
from harbor_runners.endpoints import resolve_model, validate_connection


@pytest.mark.parametrize("model,protocol", [
    ("openrouter/anthropic/claude-sonnet-4.6","chat_completions"),
    ("anthropic/claude-sonnet-4-6","messages"),
    ("openai/gpt-test","responses"),
])
def test_same_harness_uses_provider_specific_config_and_only_trial_token(tmp_path, monkeypatch, model, protocol):
    monkeypatch.setenv("OPENAI_API_KEY","host-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY","host-secret")
    monkeypatch.setenv("OPENROUTER_API_KEY","host-secret")
    monkeypatch.setenv("TOPOGYM_MODEL_API_KEY","host-secret")
    connection = resolve_model(model, version="1.18.33")
    env, options = bind(connection,url="http://127.0.0.1:321/",token="trial-only")
    assert connection["protocol"] == protocol
    overlay = options["opencode_config"]
    assert overlay["model"] == overlay["small_model"] == model
    assert overlay["enabled_providers"] == [connection["provider_id"]]
    assert overlay["provider"][connection["provider_id"]]["options"] == {
        "baseURL":"http://127.0.0.1:321/v1","apiKey":"trial-only"}
    assert json.loads(env["OPENCODE_CONFIG_CONTENT"]) == overlay
    delegate = create_delegate(connection,dict(logs_dir=tmp_path/"agent"),url="http://127.0.0.1:321",token="trial-only")
    assert delegate._version == "1.18.33"
    assert not any("host-secret" in str(source) for source in delegate._env_sources())
    assert "host-secret" not in json.dumps(delegate.model_connection.env)
    command = delegate._build_register_config_command()
    assert "host-secret" not in command and connection["model_id"] in command


def test_custom_compatible_provider_needs_explicit_sdk(tmp_path):
    path = tmp_path/"providers.yaml"
    path.write_text("""schema_version: 1
providers:
  internal:
    url: https://models.example.invalid/v1
    protocol: chat_completions
    npm: '@ai-sdk/openai-compatible'
""")
    c = resolve_model("internal/some-model",version="1.18.33",path=path)
    env, options = bind(c,url="http://127.0.0.1:1",token="trial")
    assert options["opencode_config"]["provider"]["internal"]["npm"] == "@ai-sdk/openai-compatible"
    path.write_text(path.read_text().replace("    npm: '@ai-sdk/openai-compatible'\n",""))
    with pytest.raises(ValueError, match="Custom providers"):
        resolve_model("internal/some-model",version="1.18.33",path=path)
