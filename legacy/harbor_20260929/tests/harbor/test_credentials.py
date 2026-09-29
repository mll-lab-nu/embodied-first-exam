"""Credentials belong to one launch, never to a frozen run or global process state."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from harbor_runners.agents.credentials import load_credentials, credential_environment, selected_secrets, redact
from harbor_runners.endpoints import CREDENTIAL_ENV
from harbor_runners.run import main

ROOT = Path(__file__).resolve().parents[2]


def private_file(root, text):
    path = root / ".secrets/harbor.env"
    path.parent.mkdir(exist_ok=True)
    path.write_text(text)
    path.chmod(0o600)
    return path


def test_loading_is_literal_and_does_not_mutate_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_EXISTING","shell-value")
    monkeypatch.delenv(CREDENTIAL_ENV,raising=False)
    literal = "$(touch should-not-exist)-${TEST_EXISTING}"
    private_file(tmp_path, f"TEST_EXISTING=file-value\n{CREDENTIAL_ENV}='{literal}'\n")
    values = load_credentials(tmp_path)
    assert values["TEST_EXISTING"] == "file-value" and values[CREDENTIAL_ENV] == literal
    assert os.environ["TEST_EXISTING"] == "shell-value" and CREDENTIAL_ENV not in os.environ
    assert not (tmp_path/"should-not-exist").exists()


def test_default_optional_but_explicit_file_required(tmp_path):
    assert load_credentials(tmp_path) == {}
    with pytest.raises(FileNotFoundError):
        load_credentials(tmp_path,tmp_path/"missing.env")


def test_non_private_file_rejected_before_loading(tmp_path,monkeypatch):
    monkeypatch.delenv(CREDENTIAL_ENV,raising=False)
    path=private_file(tmp_path,f"{CREDENTIAL_ENV}=test-secret\n")
    path.chmod(0o644)
    with pytest.raises(ValueError,match="600"):
        load_credentials(tmp_path)
    assert CREDENTIAL_ENV not in os.environ


@pytest.mark.parametrize("bad", ["BROKEN='test-secret", "test-secret", "TOPOGYM_MODEL_API_KEY=test-secret"])
def test_invalid_file_does_not_leak_or_partially_load(tmp_path,monkeypatch,bad,capsys):
    monkeypatch.delenv(CREDENTIAL_ENV,raising=False)
    private_file(tmp_path,f"{CREDENTIAL_ENV}=first-secret\n"+bad+"\n")
    with pytest.raises(ValueError) as error:
        load_credentials(tmp_path)
    assert "secret" not in str(error.value) and CREDENTIAL_ENV not in os.environ
    assert not capsys.readouterr().err


def test_explicit_key_overrides_environment_and_file_with_concurrent_isolation(tmp_path,monkeypatch):
    private_file(tmp_path,f"{CREDENTIAL_ENV}=file-key\n")
    monkeypatch.setenv(CREDENTIAL_ENV,"shell-key")
    assert credential_environment(tmp_path)[CREDENTIAL_ENV] == "shell-key"
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda k:credential_environment(tmp_path,api_key=k),["first-key","second-key"]))
    assert [env[CREDENTIAL_ENV] for env in results] == ["first-key","second-key"]
    assert os.environ[CREDENTIAL_ENV] == "shell-key"
    assert redact("first-key",selected_secrets(results[0])) == "[REDACTED]"


@pytest.mark.parametrize("key", ["", "has space", "newline\n", "not-ascii-中"])
def test_invalid_key_has_no_literal_in_error(tmp_path,monkeypatch,key):
    monkeypatch.delenv(CREDENTIAL_ENV,raising=False)
    with pytest.raises(ValueError):
        credential_environment(tmp_path,api_key=key)


def test_prepare_needs_no_key_or_environment_file_and_freezes_no_secret(tmp_path,monkeypatch):
    monkeypatch.delenv(CREDENTIAL_ENV,raising=False)
    secret="private-value-only-for-this-test"
    assert main(["prepare","--root",str(tmp_path),"--model-name","openrouter/test/model",
                 "--api-key",secret,"--env-file",str(tmp_path/"missing"),"--run-id","frozen"]) == 0
    run=tmp_path/"runs/harbor/frozen"
    assert all(secret not in p.read_text() for p in run.rglob("*") if p.is_file())
    assert CREDENTIAL_ENV not in os.environ


def test_missing_key_rejected_before_creating_run(tmp_path,monkeypatch,capsys):
    monkeypatch.delenv(CREDENTIAL_ENV,raising=False)
    assert main(["run","--root",str(tmp_path),"--model-name","openrouter/test/model"]) == 2
    assert not (tmp_path/"runs").exists()
    assert "Missing API key" in capsys.readouterr().err
