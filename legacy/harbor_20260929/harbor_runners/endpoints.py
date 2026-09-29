"""Resolve a full OpenCode model name once; freeze the selected provider route."""
import hashlib
import os
from pathlib import Path
import re

import yaml

from topogym.agents.usage.sources import PROTOCOLS

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_TABLE = PROJECT / "configs/harbor/providers.yaml"
CREDENTIAL_ENV = "TOPOGYM_MODEL_API_KEY"
NATIVE_PROTOCOLS = {"openrouter": "chat_completions", "anthropic": "messages", "openai": "responses"}
SDK_PROTOCOLS = {"@openrouter/ai-sdk-provider": "chat_completions", "@ai-sdk/anthropic": "messages",
                 "@ai-sdk/openai": "responses", "@ai-sdk/openai-compatible": "chat_completions"}


class UniqueLoader(yaml.SafeLoader):
    """Duplicate IDs must not silently change the selected upstream."""


def _mapping(loader, node, deep=False):
    result = {}
    for key, value in loader.construct_pairs(node, deep=deep):
        if key in result:
            raise ValueError("Duplicate key in configuration YAML")
        result[key] = value
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def read_mapping(path):
    content = Path(path).read_bytes()
    try:
        value = yaml.load(content, Loader=UniqueLoader)
    except (yaml.YAMLError, TypeError):
        raise ValueError("Invalid configuration YAML") from None
    if not isinstance(value, dict):
        raise ValueError("Configuration must be a mapping")
    return value, hashlib.sha256(content).hexdigest()


def split_model(model_name):
    # Harbor 0.23.0 inserts --model into a shell command. Never admit shell syntax.
    if not isinstance(model_name, str) or len(model_name) > 256:
        raise ValueError("Use a full model-name: provider_id/model_id")
    provider, sep, model = model_name.partition("/")
    if (not sep or re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", provider) is None
            or re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._:/@+-]*", model) is None
            or model.endswith("/") or "//" in model):
        raise ValueError("Invalid model-name; use provider_id/model_id without whitespace or shell characters")
    return provider, model


def validate_version(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value) is None:
        raise ValueError("opencode_version must be a pinned version such as 1.18.33")
    return value


def validate_provider(provider, entry):
    if (not isinstance(entry, dict) or set(entry) - {"url", "protocol", "npm"}
            or not {"url", "protocol"} <= set(entry)):
        raise ValueError("Provider needs url and protocol; only an optional npm SDK override is allowed")
    protocol = entry["protocol"]
    if not isinstance(protocol, str) or protocol not in PROTOCOLS:
        raise ValueError("Unknown provider protocol")
    PROTOCOLS[protocol].validate_route(entry)
    expected = NATIVE_PROTOCOLS.get(provider)
    if expected is not None and protocol != expected:
        raise ValueError("Protocol does not match the native OpenCode provider")
    npm = entry.get("npm")
    if npm is not None and (not isinstance(npm, str) or SDK_PROTOCOLS.get(npm) != protocol):
        raise ValueError("Unsupported SDK/protocol combination")
    if expected is None and npm is None:
        raise ValueError("Custom providers require a supported npm SDK in providers.yaml")


def resolve_model(model_name, *, version, path=None):
    provider, model = split_model(model_name)
    validate_version(version)
    path = Path(path or DEFAULT_TABLE).resolve()
    table, digest = read_mapping(path)
    if (set(table) != {"schema_version", "providers"} or type(table["schema_version"]) is not int
            or table["schema_version"] != 1 or not isinstance(table["providers"], dict)):
        raise ValueError("Invalid provider table schema")
    for identifier, entry in table["providers"].items():
        if not isinstance(identifier, str):
            raise ValueError("Provider IDs must be strings")
        if split_model(identifier + "/validation")[0] != identifier:
            raise ValueError("Invalid provider ID")
        validate_provider(identifier, entry)
    if provider not in table["providers"]:
        raise ValueError(f"Provider '{provider}' is not registered in providers.yaml")
    entry = table["providers"][provider]
    return dict(schema_version=1, full_model_name=model_name, provider_id=provider, model_id=model,
                opencode_version=version, url=entry["url"].rstrip("/"), protocol=entry["protocol"],
                npm=entry.get("npm"), source_path=str(path), source_sha256=digest)


def validate_connection(connection):
    required = {"schema_version", "full_model_name", "provider_id", "model_id", "opencode_version",
                "url", "protocol", "npm", "source_path", "source_sha256"}
    if (not isinstance(connection, dict) or set(connection) != required
            or type(connection["schema_version"]) is not int or connection["schema_version"] != 1):
        raise ValueError("Unsupported frozen model connection; prepare a new run")
    provider, model = split_model(connection["full_model_name"])
    if (provider, model) != (connection["provider_id"], connection["model_id"]):
        raise ValueError("Frozen model identity is inconsistent")
    validate_version(connection["opencode_version"])
    entry = {key: connection[key] for key in ("url", "protocol")}
    if connection["npm"] is not None:
        entry["npm"] = connection["npm"]
    validate_provider(provider, entry)
    if (not isinstance(connection["source_path"], str)
            or not isinstance(connection["source_sha256"], str)
            or re.fullmatch(r"[a-f0-9]{64}", connection["source_sha256"]) is None):
        raise ValueError("Invalid frozen provider source identity")
    return connection


def freeze_routes(connection):
    validate_connection(connection)
    provider = connection["provider_id"]
    route = dict(url=connection["url"], protocol=connection["protocol"],
                 credential_source_env=CREDENTIAL_ENV, model=connection["model_id"])
    endpoints = dict(schema_version=2, source_path=connection["source_path"],
                     source_sha256=connection["source_sha256"], endpoints={provider: route})
    binding = dict(schema_version=2, adapter_id="opencode", model=connection["full_model_name"],
                   opencode_version=connection["opencode_version"], routes={"primary": {"endpoint": provider}})
    return endpoints, binding


def routes_from_frozen(endpoints, binding):
    return {name: dict(endpoints["endpoints"][ref["endpoint"]], endpoint_id=ref["endpoint"])
            for name, ref in binding["routes"].items()}


def credential_resolver(route, environ=None):
    value = (os.environ if environ is None else environ).get(CREDENTIAL_ENV)
    if not value:
        raise ValueError("Missing API key; supply --api-key, --api-key-stdin, or TOPOGYM_MODEL_API_KEY")
    if not isinstance(value, str) or any(ord(c) < 33 or ord(c) > 126 for c in value):
        raise ValueError("API key must contain printable non-whitespace ASCII characters")
    return value
