"""Literal-secret redaction at the runner boundary, independent of agent type."""
import os
from pathlib import Path
import re
import stat
import tempfile
from harbor_runners.endpoints import CREDENTIAL_ENV, credential_resolver


def load_credentials(root, env_file=None):
    """Read a private dotenv file without changing the process environment.

    No shell execution or variable interpolation. Never log returned values.
    The default file is optional; an explicitly requested file must exist.
    """
    from dotenv.parser import parse_stream

    path = Path(env_file).expanduser() if env_file is not None else Path(root) / ".secrets/harbor.env"
    if env_file is None and not path.exists():
        return {}
    values = {}
    with path.open(encoding="utf-8") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            raise ValueError("Credentials file must be a private regular file; set permissions to 600")
        try:
            for item in parse_stream(stream):
                if item.error:
                    raise ValueError(f"Invalid credentials file syntax at line {item.original.line}")
                if item.key is None:
                    continue
                if (re.fullmatch(r"[A-Z][A-Z0-9_]*", item.key) is None
                        or item.value is None or "\0" in item.value or item.key in values):
                    raise ValueError(f"Invalid or duplicate credentials entry at line {item.original.line}")
                values[item.key] = item.value
        except UnicodeError:
            raise ValueError("Credentials file must use UTF-8") from None
    return values


def credential_environment(root, env_file=None, *, api_key=None, required=True):
    # Explicit input > process env > private file; each launch owns its copy.
    environment = {**load_credentials(root, env_file), **os.environ}
    if api_key is not None:
        environment[CREDENTIAL_ENV] = api_key
    if required or environment.get(CREDENTIAL_ENV):
        credential_resolver({}, environment)
    return environment


def selected_secrets(environment=None):
    value = (os.environ if environment is None else environment).get(CREDENTIAL_ENV)
    return (value,) if value else ()


def redact(text, secrets):
    for secret in secrets:
        text = text.replace(secret, "[REDACTED]")
    return text


def redact_logs(run, secrets):
    """Scrub native text logs. Never alter hashed simulator evidence silently.

    An adapter emitting a secret into sealed evidence is a collection failure;
    do not rewrite source identity/media hashes and call it the same experiment.
    """
    if not secrets:
        return
    text_types = {".json", ".jsonl", ".log", ".txt", ".md", ".yaml", ".toml", ".py", ".sh"}
    for path in (Path(run) / "jobs").rglob("*"):
        if path.is_symlink() or not path.is_file() or path.suffix not in text_types:
            continue
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".redact-")
        changed = False
        try:
            with path.open(errors="replace") as source, os.fdopen(fd, "w") as target:
                for line in source:
                    scrubbed = redact(line, secrets)
                    changed |= scrubbed != line
                    target.write(scrubbed)
            if changed:
                os.chmod(temporary, path.stat().st_mode & 0o777)
                os.replace(temporary, path)
                # Hashed evidence now fails integrity validation instead of
                # silently changing the identity of the submitted policy.
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
