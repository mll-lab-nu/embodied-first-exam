"""Gateway configuration and real HTTP adapter checks without subscription use."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading

import pytest

from humanclaw_bench.experiments.integration import resolved_model_settings
from humanclaw_bench.harnesses.runtime import load_harness_config, native_connection
from humanclaw_bench.vlm.api_check import check_model_api
from humanclaw_bench.vlm.endpoints import validate_base_url
from humanclaw_bench.vlm.factory import build_model


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    for name in ("MAGPIE_BASE_URL", "MAGPIE_API_KEY", "MAGPIE_MODEL"):
        monkeypatch.delenv(name, raising=False)


def model_config():
    return json.loads((ROOT / "configs/models/magpie_codex_astra.json").read_text())


@contextmanager
def gateway(status=200):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            requests.append((self.path, {key.lower(): value for key, value in self.headers.items()},
                             json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            payload = {"id": "chatcmpl-test", "object": "chat.completion", "created": 0,
                       "model": "codex/gpt-6-astra", "choices": [{"index": 0, "finish_reason": "stop",
                       "message": {"role": "assistant", "content": '{"status":"ok","image_color":"red"}'}}],
                       "usage": {"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19}}
            if status != 200:
                payload = {"error": {"message": "private-provider-response-must-not-be-printed", "type": "authentication_error"}}
            encoded = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("status", [200, 401, 429])
def test_magpie_template_uses_real_adapter_and_reports_failures_safely(monkeypatch, status):
    pytest.importorskip("openai")
    monkeypatch.setenv("MAGPIE_API_KEY", "test-private-gateway-key")
    with gateway(status) as (url, requests):
        monkeypatch.setenv("MAGPIE_BASE_URL", url)
        result = check_model_api(ROOT / "configs/models/magpie_codex_astra.json", timeout=5)
    assert result["passed"] is (status == 200)
    assert len(requests) == 1  # No retry or cloud fallback, including 429.
    path, headers, body = requests[0]
    assert path == "/v1/chat/completions"
    assert headers["authorization"] == "Bearer test-private-gateway-key"
    assert body["model"] == "codex/gpt-6-astra"
    assert body["reasoning_effort"] == "medium"
    assert body["response_format"] == {"type": "json_object"}
    assert not ({"temperature", "max_tokens", "max_completion_tokens"} & body.keys())
    assert body["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
    if status != 200:
        assert result["error"]["http_status"] == status
        assert "Azure" not in result["error"]["hint"]
    else:
        assert result["usage"]["total_tokens"] == 19
    assert "test-private-gateway-key" not in json.dumps(result)
    assert "private-provider-response" not in json.dumps(result)


def test_missing_explicit_endpoint_never_falls_back_to_another_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://other-provider.invalid/v1")
    monkeypatch.setenv("MAGPIE_API_KEY", "test-key")
    for operation in (lambda: build_model(model_config(), tmp_path),
                      lambda: resolved_model_settings(model_config())):
        with pytest.raises(ValueError, match="MAGPIE_BASE_URL"):
            operation()


def test_gateway_key_is_required_even_with_a_custom_endpoint(monkeypatch, tmp_path):
    monkeypatch.setenv("MAGPIE_BASE_URL", "http://127.0.0.1:3425/v1")
    with pytest.raises(RuntimeError, match="MAGPIE_API_KEY"):
        build_model(model_config(), tmp_path)


def test_recorded_model_settings_match_deployer_overrides(monkeypatch):
    monkeypatch.setenv("MAGPIE_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("MAGPIE_MODEL", "codex/account-model")
    settings = resolved_model_settings(model_config())
    assert settings["base_url"] == "https://gateway.example/v1"
    assert settings["model"] == "codex/account-model"
    assert settings["send_max_tokens"] is False


@pytest.mark.parametrize("url", ["ftp://gateway/v1", "http:///v1", "https://user:secret@gateway/v1",
                                 "https://gateway/v1?key=secret", "https://gateway/v1#secret",
                                 "https://gateway:bad/v1", " http://gateway/v1", "http://gateway:0/v1"])
def test_bad_urls_fail_without_echoing_credentials(url):
    with pytest.raises(ValueError) as error:
        validate_base_url(url)
    assert "secret" not in str(error.value)


def test_native_gateway_requires_explicit_http_opt_in_and_bearer_key(monkeypatch):
    config = load_harness_config(ROOT / "configs/harnesses/magpie_native.json")
    with pytest.raises(ValueError, match="MAGPIE_BASE_URL"):
        native_connection(config)
    monkeypatch.setenv("MAGPIE_BASE_URL", "http://10.0.0.10:3425/v1")
    monkeypatch.setenv("MAGPIE_API_KEY", "test-key")
    assert native_connection(config) == ("http://10.0.0.10:3425/v1", "test-key")
    with pytest.raises(ValueError, match="requires HTTPS"):
        native_connection({**config, "allow_http": False})
    monkeypatch.delenv("MAGPIE_API_KEY")
    with pytest.raises(ValueError, match="MAGPIE_API_KEY"):
        native_connection(config)


def test_native_cloud_default_still_requires_https(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
    config = {"responses_base_url": "https://azure.example/openai/v1"}
    assert native_connection(config) == (config["responses_base_url"], "test-key")
    with pytest.raises(ValueError, match="requires HTTPS"):
        native_connection({"responses_base_url": "http://azure.example/openai/v1"})


@pytest.mark.parametrize("fields", [{"allow_http": "false"}, {"auth": "typo"},
                                  {"responses_base_url": "https://user:secret@gateway/v1"}])
def test_native_config_rejects_ambiguous_connection_settings(fields, tmp_path):
    path = tmp_path / "harness.json"
    path.write_text(json.dumps(fields))
    with pytest.raises(ValueError):
        load_harness_config(path)
