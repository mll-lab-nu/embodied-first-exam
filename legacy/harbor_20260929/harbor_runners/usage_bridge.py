"""Fixed OpenCode lifecycle configuration; the usage core remains harness independent."""
import hashlib
from pathlib import Path

from topogym.agents.usage.config import validate_usage
from .endpoints import validate_connection


def socket_directory(run):
    digest = hashlib.sha256(str(Path(run).resolve()).encode()).hexdigest()[:20]
    return Path("/tmp") / ("topogym-usage-" + digest)


def require_capabilities(connection, usage):
    settings = validate_usage(usage)
    if settings["mode"] == "strict":
        raise ValueError("strict requires verified input upper bounds; use observed")
    if settings["mode"] != "observed":
        raise ValueError("OpenCode requires observed usage; off is reserved for Scripted tests")
    validate_connection(connection)
    from harbor.agents.installed.opencode import OpenCode
    OpenCode.parse_options({"version": connection["opencode_version"]}, {})


def wrap_agent(connection, usage, run):
    require_capabilities(connection, usage)
    return dict(import_path="harbor_runners.agents.usage_adapter:UsageAgent",
        model_name=connection["full_model_name"], env={}, kwargs=dict(connection=connection,
            usage=validate_usage(usage), sockets=str(socket_directory(run))))
