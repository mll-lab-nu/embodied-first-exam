"""Resolve deployer-owned API addresses without reading or logging credentials."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit


def configured_base_url(config: dict[str, Any], field: str = "base_url") -> str | None:
    """An explicit URL environment variable is required, never a cloud fallback."""
    env_name = config.get(field + "_env")
    value = config.get(field)
    if env_name is not None:
        if not isinstance(env_name, str) or not env_name.strip():
            raise ValueError(f"{field}_env must be a nonempty environment variable name")
        value = os.environ.get(env_name)
        if not value or not value.strip():
            raise ValueError(f"Missing endpoint environment variable: {env_name}")
    if value is None:
        return None
    return validate_base_url(value, field=field)


def validate_base_url(value: str, *, field: str = "base_url", allow_http: bool = True) -> str:
    """Reject malformed addresses and credentials embedded in recorded URLs."""
    try:
        if not isinstance(value, str) or value != value.strip() or any(c.isspace() for c in value):
            raise ValueError
        parsed = urlsplit(value)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment):
            raise ValueError
        if parsed.port is not None and parsed.port < 1:
            raise ValueError
    except ValueError:
        # The address itself may contain a mistakenly pasted credential.
        raise ValueError(f"{field} must be an HTTP(S) base URL without credentials, query or fragment") from None
    if parsed.scheme == "http" and not allow_http:
        raise ValueError(f"{field} requires HTTPS; set allow_http=true only for an explicitly trusted gateway")
    return value
