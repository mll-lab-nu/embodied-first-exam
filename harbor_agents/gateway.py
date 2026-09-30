"""Keep the OpenRouter key out of the agent's reach: a model gateway beside the harness holds it.

`start_gateway` uploads `llm_gateway.py` (the team's model gateway, as on dev/qineng) into the task container and starts
it on 127.0.0.1. It reads the key from a file and deletes it at start, pins the model on every request, and logs every
exchange to the trial's agent/gateway.jsonl. The harness is given the gateway's URL and `PLACEHOLDER_KEY`, so neither
its environment nor its auth file holds a credential the agent could use for anything else.
"""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

from harbor.models.trial.paths import EnvironmentPaths

PORT = 8787
URL = f"http://127.0.0.1:{PORT}"
PLACEHOLDER_KEY = "rcb-model-gateway"
_DIR = PurePosixPath("/tmp/rcb-gateway")
_SOURCE = Path(__file__).with_name("llm_gateway.py")


async def start_gateway(agent, environment, key: str | None, model: str) -> None:
    """Start the gateway for `agent` (a Harbor installed agent) and wait until it answers; `model` is OpenRouter's id."""
    if not key:
        raise ValueError(f"{type(agent).__name__} needs OPENROUTER_API_KEY (--env-file .env)")
    logs = EnvironmentPaths.agent_dir.as_posix()
    await agent.exec_as_agent(environment, command=f"mkdir -p {_DIR} {logs}")
    for name, text in (("llm_gateway.py", _SOURCE.read_text()), ("key", key), ("config.json", json.dumps({"model": model}))):
        await agent._upload_config_text(environment, content=text, remote_path=f"{_DIR}/{name}", filename=name)
    await agent.exec_as_agent(environment, command=(
        f"(setsid nohup python3 {_DIR}/llm_gateway.py --port {PORT} --key-file {_DIR}/key --config-file {_DIR}/config.json "
        f"--log {logs}/gateway.jsonl > {logs}/gateway.err 2>&1 < /dev/null &); "
        f"for i in $(seq 1 100); do python3 -c \"import urllib.request; urllib.request.urlopen('{URL}/healthz', timeout=1)\" "
        f"2>/dev/null && exit 0; sleep 0.2; done; echo 'model gateway did not start' >&2; exit 1"))
