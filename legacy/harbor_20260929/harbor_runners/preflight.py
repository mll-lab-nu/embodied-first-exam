"""Checks before model invocation; never print credentials."""
from importlib.metadata import version
import json
import os
from pathlib import Path
import subprocess
import sys

from . import HARBOR_VERSION
from .task_generator import verify_frozen, file_hash
from .usage_bridge import require_capabilities
from .endpoints import credential_resolver, routes_from_frozen, freeze_routes


def check(run, *, docker=True, environ=None):
    manifest = verify_frozen(run)
    if version("harbor") != HARBOR_VERSION or manifest["harbor_version"] != HARBOR_VERSION:
        raise ValueError(f"Use locked Harbor {HARBOR_VERSION}; run scripts/setup_harbor_runner.sh")
    config = json.loads((Path(run) / "experiment.resolved.json").read_text())
    if manifest["schema_version"] != 2 or "execution" not in config:
        raise ValueError("Legacy run configuration; use its original checkout or prepare a new run")
    if config["execution"]["harness"] == "opencode":
        require_capabilities(config.get("model_connection"), config["usage"])
    elif config["execution"]["harness"] != "scripted" or config["usage"]["mode"] != "off":
        raise ValueError("Invalid frozen execution mode")
    source_path = Path(run) / "usage_sources.resolved.json"
    source_hashes = json.loads(source_path.read_text()) if source_path.exists() else {}
    rollout_source_path = Path(run) / "rollout_sources.resolved.json"
    rollout_sources = json.loads(rollout_source_path.read_text()) if rollout_source_path.exists() else {}
    project = Path(__file__).resolve().parents[1]
    for relative, expected in {**source_hashes, **rollout_sources}.items():
        if file_hash(project / relative) != expected:
            raise ValueError("Prepared usage or rollout source changed; prepare a new run")
    endpoints_path = Path(run) / "agent_urls.resolved.json"
    if config["usage"]["mode"] != "off" and not endpoints_path.exists():
        raise ValueError("Legacy budget run has no frozen endpoints; prepare a new run before launch")
    if config["usage"]["mode"] != "off" and endpoints_path.exists():
        endpoints = json.loads(endpoints_path.read_text())
        binding = json.loads((Path(run) / "usage_binding.resolved.json").read_text())
        if (endpoints, binding) != freeze_routes(config["model_connection"]):
            raise ValueError("Frozen model connection and routing disagree")
        routes = routes_from_frozen(endpoints, binding)
        for route in routes.values():
            credential_resolver(route, environ)
    identity = None
    if docker:
        if config["usage"]["mode"] != "off":
            endpoint = os.environ.get("DOCKER_HOST")
            if not endpoint:
                context = subprocess.run(["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
                    text=True, capture_output=True, timeout=20)
                if context.returncode:
                    raise RuntimeError("Cannot determine Docker endpoint for usage socket mount")
                endpoint = context.stdout.strip()
            if sys.platform != "linux" or not endpoint.startswith("unix://"):
                raise ValueError("Budgeted trials currently require a local Linux Docker daemon")
        for command in (["docker", "info", "--format", "{{.ServerVersion}}"],
                        ["docker", "compose", "version", "--short"]):
            result = subprocess.run(command, text=True, capture_output=True, timeout=20)
            if result.returncode:
                raise RuntimeError("Docker daemon/Compose unavailable to this user; check docker info and docker compose version")
        result = subprocess.run(["docker", "image", "inspect", config["image"]],
                                text=True, capture_output=True, timeout=20)
        if result.returncode:
            raise RuntimeError("Shared image is missing locally; build or pull it before launch")
        image = json.loads(result.stdout)[0]
        identity = dict(id=image["Id"], repo_digests=image.get("RepoDigests", []))
        marker = Path(run) / "image.resolved.json"
        if marker.exists() and json.loads(marker.read_text()) != identity:
            raise ValueError("Shared image tag changed since preflight")
        marker.write_text(json.dumps(identity, indent=2) + "\n")
        # CPU-only image probe validates the actual installed SimulatorConfig and
        # catalog. It does not call make/reset, initialize CUDA, or contact a model.
        probe = '''import hashlib,json,sys
from pathlib import Path
import topogym.agents.usage
import topogym
import harbor_runners
from topogym import SimulatorConfig
from topogym.config import variation_records
from topogym.config.registry import variation_registration
from topogym.agents.usage import BudgetPolicy, UsageLedger
catalog_hash=hashlib.sha256(Path(variation_records.__file__).read_bytes()).hexdigest()
payload=json.load(sys.stdin)
for relative,expected in payload['usage_sources'].items():
 if relative.startswith('harbor_runners/'):
  source=Path(harbor_runners.__file__).parent / relative.removeprefix('harbor_runners/')
 else:
  source=Path(topogym.agents.usage.__file__).parent / relative.removeprefix('topogym/agents/usage/')
 assert hashlib.sha256(source.read_bytes()).hexdigest()==expected, 'Shared image usage source differs from prepared source'
for relative,expected in payload['rollout_sources'].items():
 source=Path(topogym.__file__).parent / relative.removeprefix('topogym/')
 assert hashlib.sha256(source.read_bytes()).hexdigest()==expected, 'Shared image rollout source differs from prepared source'
for item in payload['instances']:
 SimulatorConfig(**item['simulator'])
 if item.get('fixture'):
  for filename,expected in item['_fixture_files'].items():
   source=Path('/opt/topogym-fixtures/fixtures',filename)
   assert source.is_file(), 'Missing fixture'
   assert hashlib.sha256(source.read_bytes()).hexdigest()==expected, 'Shared image fixture differs from source'
 if not item.get('fixture'):
  assert item['catalog']['sha256']==catalog_hash, 'Shared image catalog differs from prepared source'
  record=variation_registration(item['simulator']['task_id'],item['simulator']['variation_id'])
  assert record['status']=='integrated'
print(json.dumps({'simulator_config':'valid','catalog_sha256':catalog_hash}))
'''
        instances = json.loads(json.dumps(config["instances"]))
        for item in instances:
            if item.get("fixture"):
                names = {item["fixture"] + ".py", "cube_transfer.py"}
                item["_fixture_files"] = {name: file_hash(Path(__file__).resolve().parents[1] /
                    "tests/fixtures" / name) for name in names}
        result = subprocess.run(["docker", "run", "--rm", "-i", "--network", "none",
            config["image"], "python", "-c", probe], input=json.dumps(dict(instances=instances,
                usage_sources=source_hashes, rollout_sources=rollout_sources)),
            text=True, capture_output=True, timeout=60)
        if result.returncode:
            raise RuntimeError("Shared image config/catalog probe failed; rebuild the image from this checkout")
    return dict(harbor_version=HARBOR_VERSION, image=identity,
                tasks=manifest["task_count"], trials=manifest["expected_trials"])
