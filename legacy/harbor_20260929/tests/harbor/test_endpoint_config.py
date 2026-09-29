"""Provider routing is selected once and remains frozen independently of credentials."""
import copy
import json
from pathlib import Path

import pytest
import yaml

from harbor_runners.config import load_config
from harbor_runners.endpoints import resolve_model, freeze_routes, routes_from_frozen, CREDENTIAL_ENV
from harbor_runners.preflight import check
from harbor_runners.task_generator import prepare, verify_frozen
from harbor_runners.agents.usage_adapter import UsageAgent

ROOT = Path(__file__).resolve().parents[2]


def table(tmp_path, **edit):
    entry = {"url": "https://example.invalid/v1", "protocol": "messages", **edit}
    path = tmp_path / "providers.yaml"
    path.write_text(yaml.safe_dump({"schema_version": 1, "providers": {"anthropic": entry}}))
    return path


def test_full_model_selects_provider_and_preserves_nested_model_id(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://unrelated.invalid")
    c = resolve_model("openrouter/anthropic/claude-sonnet-4.6", version="1.18.33")
    assert c["provider_id"] == "openrouter"
    assert c["model_id"] == "anthropic/claude-sonnet-4.6"
    assert c["url"] == "https://openrouter.ai/api/v1"
    endpoints, binding = freeze_routes(c)
    route = routes_from_frozen(endpoints, binding)["primary"]
    assert route["model"] == c["model_id"] and route["credential_source_env"] == CREDENTIAL_ENV


@pytest.mark.parametrize("bad", ["https://name:secret@example.invalid/v1",
    "https://example.invalid/v1?api_key=secret", "http://example.invalid/v1",
    "https://example.invalid:bad/v1", "https://example.invalid/\n"])
def test_bad_url_rejected_before_preparing(tmp_path, bad):
    with pytest.raises(ValueError):
        resolve_model("anthropic/fixture", version="1.18.33", path=table(tmp_path, url=bad))


@pytest.mark.parametrize("edit", [{"protocol":"unknown"}, {"protocol":"responses"},
    {"api_key":"secret"}, {"npm":"unreviewed-package"}])
def test_invalid_provider_entry(tmp_path, edit):
    with pytest.raises(ValueError):
        resolve_model("anthropic/fixture", version="1.18.33", path=table(tmp_path, **edit))


def test_duplicate_yaml_keys_rejected(tmp_path):
    path = table(tmp_path)
    path.write_text("schema_version: 1\nschema_version: 1\nproviders: {}\n")
    with pytest.raises(ValueError, match="Duplicate"):
        resolve_model("anthropic/fixture", version="1.18.33", path=path)


def test_prepare_freezes_url_after_table_deleted_and_environment_changed(tmp_path, monkeypatch):
    config = load_config(overrides={"model":"anthropic/fixture"})
    path = table(tmp_path)
    config["providers_file"] = str(path)
    run = prepare(config, tmp_path, "freeze")
    path.unlink()
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://changed.invalid")
    verify_frozen(run)
    with pytest.raises(ValueError, match="API key"):
        check(run, docker=False, environ={})
    assert check(run, docker=False, environ={CREDENTIAL_ENV:"test-secret"})["trials"] == 1
    kwargs = json.loads((run / "job.json").read_text())["agents"][0]["kwargs"]
    agent = UsageAgent(**kwargs, logs_dir=tmp_path/"trial/agent", model_name="anthropic/fixture")
    assert agent._resolved_routes()["primary"]["url"] == "https://example.invalid/v1"
    assert "test-secret" not in "".join(p.read_text() for p in run.rglob("*") if p.is_file())
    (run / "agent_urls.resolved.json").write_text("{}")
    with pytest.raises(ValueError, match="changed"):
        verify_frozen(run)


def test_scripted_does_not_read_provider_table_or_require_key(tmp_path):
    config = load_config(ROOT/"configs/harbor/experiments/smoke_scripted.yaml")
    config["providers_file"] = str(tmp_path/"missing.yaml")
    run = prepare(config, tmp_path, "scripted", scripted_scenario="normal")
    assert not (run/"agent_urls.resolved.json").exists()
    assert check(run, docker=False, environ={})["trials"] == 1
    job = json.loads((run/"job.json").read_text())
    assert job["agents"][0]["import_path"].endswith(":ScriptedAgent")


def test_custom_deployment_paths_resolve_relative_to_defaults(tmp_path):
    preset = load_config()
    for key in ("providers_file", "image", "opencode_version", "gpus"):
        preset.pop(key, None)
    (tmp_path/"experiment.yaml").write_text(yaml.safe_dump(preset))
    defaults = tmp_path/"defaults.yaml"
    defaults.write_text(yaml.safe_dump(dict(schema_version=1, experiment_config="experiment.yaml",
        image="example:locked", opencode_version="1.18.33", providers_file="providers.yaml")))
    c = load_config(defaults_file=defaults)
    assert c["providers_file"] == str(tmp_path/"providers.yaml") and c["image"] == "example:locked"


def test_retired_profile_configuration_has_migration_error(tmp_path):
    path = tmp_path/"old.yaml"
    path.write_text("agent_profile: removed.yaml\n")
    with pytest.raises(ValueError, match="profiles are retired"):
        load_config(path)


def test_malformed_frozen_connection_rejected_without_live_table(tmp_path):
    config = load_config(overrides={"model":"anthropic/fixture"})
    run = prepare(config,tmp_path,"identity")
    connection = json.loads((run/"experiment.resolved.json").read_text())["model_connection"]
    connection["model_id"] = "different"
    with pytest.raises(ValueError, match="identity"):
        freeze_routes(connection)
