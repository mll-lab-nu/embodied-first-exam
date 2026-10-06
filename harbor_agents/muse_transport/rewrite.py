"""Provider-safe function-name rewriting."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any

MAX_TOOL_NAME_LENGTH = 64
_HASH_LENGTH = 12
ENCRYPTED_REPLAY_TYPES = frozenset({"reasoning", "compaction"})


def alias_tool_name(name: str, max_length: int = MAX_TOOL_NAME_LENGTH) -> str:
    """Return a deterministic function name no longer than ``max_length``."""
    if max_length < 1:
        raise ValueError("max_length must be positive")
    if len(name) <= max_length:
        return name
    digest = hashlib.sha256(name.encode()).hexdigest()[:_HASH_LENGTH]
    if max_length <= _HASH_LENGTH:
        return digest[:max_length]
    return f"{name[: max_length - _HASH_LENGTH - 1]}_{digest}"


def collect_tool_name_map(payload: Any) -> dict[str, str]:
    """Collect overlong function names declared in a Responses request."""
    if not isinstance(payload, dict) or not isinstance(payload.get("tools"), list):
        return {}
    names: set[str] = set()
    pending: list[Any] = list(payload["tools"])
    while pending:
        value = pending.pop()
        if isinstance(value, list):
            pending.extend(value)
        elif isinstance(value, dict):
            pending.extend(value.values())
            name = value.get("name")
            if isinstance(name, str) and len(name) > MAX_TOOL_NAME_LENGTH:
                names.add(name)
    return {name: alias_tool_name(name) for name in sorted(names)}


def _rewrite_names(value: Any, mapping: dict[str, str]) -> Any:
    if isinstance(value, list):
        return [_rewrite_names(item, mapping) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: mapping.get(item, item)
        if key == "name" and isinstance(item, str)
        else _rewrite_names(item, mapping)
        for key, item in value.items()
    }


def rewrite_request(payload: Any) -> tuple[Any, dict[str, str]]:
    """Shorten declarations and return the response alias-to-original map."""
    original_to_alias = collect_tool_name_map(payload)
    if not original_to_alias:
        return payload, {}
    rewritten = _rewrite_names(deepcopy(payload), original_to_alias)
    return rewritten, {alias: original for original, alias in original_to_alias.items()}


def encrypted_replay_item_id(value: Any) -> str | None:
    """Return a content-safe identity for model-bound Responses API state."""
    if not isinstance(value, dict):
        return None
    item_type = value.get("type")
    if not isinstance(item_type, str) or item_type not in ENCRYPTED_REPLAY_TYPES:
        return None
    encrypted_content = value.get("encrypted_content")
    if not isinstance(encrypted_content, str) or not encrypted_content:
        return None
    material = f"{item_type}\0{encrypted_content}".encode()
    return hashlib.sha256(material).hexdigest()


def collect_encrypted_replay_ids(payload: Any) -> set[str]:
    """Collect identities without exposing or retaining encrypted payload content."""
    identities: set[str] = set()
    pending = [payload]
    while pending:
        value = pending.pop()
        identity = encrypted_replay_item_id(value)
        if identity is not None:
            identities.add(identity)
            continue
        if isinstance(value, list):
            pending.extend(value)
        elif isinstance(value, dict):
            pending.extend(value.values())
    return identities


_DROP = object()


def _filter_encrypted_replay_items(value: Any, blocked_ids: set[str]) -> tuple[Any, int]:
    identity = encrypted_replay_item_id(value)
    if identity is not None and identity in blocked_ids:
        return _DROP, 1
    if isinstance(value, list):
        rewritten: list[Any] = []
        removed = 0
        for item in value:
            filtered, count = _filter_encrypted_replay_items(item, blocked_ids)
            removed += count
            if filtered is not _DROP:
                rewritten.append(filtered)
        return (rewritten if removed else value), removed
    if isinstance(value, dict):
        rewritten_dict: dict[Any, Any] = {}
        removed = 0
        for key, item in value.items():
            filtered, count = _filter_encrypted_replay_items(item, blocked_ids)
            removed += count
            if filtered is not _DROP:
                rewritten_dict[key] = filtered
        return (rewritten_dict if removed else value), removed
    return value, 0


def filter_encrypted_replay_items(
    payload: Any, blocked_ids: set[str]
) -> tuple[Any, int]:
    """Remove encrypted reasoning/compaction items identified as model-incompatible."""
    if not blocked_ids:
        return payload, 0
    filtered, removed = _filter_encrypted_replay_items(payload, blocked_ids)
    return ({} if filtered is _DROP else filtered), removed


def restore_response(payload: Any, alias_to_original: dict[str, str]) -> Any:
    """Restore Muse Code's function names in a provider response event."""
    return _rewrite_names(payload, alias_to_original) if alias_to_original else payload
