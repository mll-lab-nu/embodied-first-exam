"""Explicit model contract and immutable owned-SDK source identity."""
import hashlib
import json
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[3] / "harnesses" / "pi-adaptive"


def adaptive_enabled(config):
    """Test explicit selection of the owned adaptive SDK runtime."""
    return config.get("pi_profile") == "adaptive-v1"


def resolve_profile(config, model=None):
    """Validate deployment capabilities and reject removed prototype settings."""
    selection = config.get("pi_profile", "native")
    if selection not in {"native", "adaptive-v1"}:
        raise ValueError("pi_profile must be native or adaptive-v1; the embodied prototype was replaced")
    if selection == "native":
        if "pi_adaptive" in config:
            raise ValueError("pi_adaptive requires pi_profile=adaptive-v1")
        return None
    if config.get("pi_source") or config.get("pi_command"):
        raise ValueError("adaptive-v1 uses its pinned SDK")
    options = config.get("pi_adaptive", {})
    if not isinstance(options, dict) or set(options) - {"model_capabilities", "recent_exchanges", "trim_at_exchanges"}:
        raise ValueError("Unknown pi_adaptive settings")
    caps = options.get("model_capabilities")
    if not isinstance(caps, dict) or set(caps) != {"model", "api", "effort_map", "max_images", "image_token_reserve", "max_input_tokens"}:
        raise ValueError("Explicit model_capabilities are required")
    if caps["api"] != "openai-responses" or not isinstance(caps["model"], str) or not caps["model"]:
        raise ValueError("Declare the actual Responses deployment")
    efforts = caps["effort_map"]
    if not isinstance(efforts, dict) or set(efforts) != {"medium", "high"} or any(v not in {"low", "medium", "high", "xhigh"} for v in efforts.values()) or efforts["medium"] == efforts["high"]:
        raise ValueError("Distinct medium/high provider effort mappings required")
    for k in ("max_images", "image_token_reserve", "max_input_tokens"):
        if type(caps[k]) is not int or caps[k] < (0 if k == "max_images" else 1):
            raise ValueError(f"Invalid model_capabilities.{k}")
    recent, trim = options.get("recent_exchanges", 8), options.get("trim_at_exchanges", 16)
    if any(type(v) is not int or v < 1 for v in (recent, trim)) or recent > trim:
        raise ValueError("Invalid context window projection")
    window, output = int(config.get("context_window", 131072)), (model or {}).get("max_tokens", 4096)
    if type(output) is not int or output < 1 or caps["max_input_tokens"] + output > window:
        raise ValueError("Delivered input/output limits must fit the context window")
    if model and (model["model"] != caps["model"] or model.get("send_max_tokens") is False):
        raise ValueError("Model identity/output limit does not match declared capabilities")
    return {"version": "pi-adaptive-v1", "pi_version": "1.3.0", "context_management": True,
        "model_capabilities": caps, "base_effort": "medium", "high_effort": "high",
        "recent_exchanges": recent, "trim_at_exchanges": trim, "context_window": window, "max_output_tokens": output}


def package_identity():
    """Require pinned SDK packages and hash all owned orchestration sources."""
    versions = {}
    for name in ("pi-coding-agent", "pi-agent-core", "pi-ai", "pi-mcp"):
        path = PACKAGE / "node_modules" / "@earendil-works" / name / "package.json"
        if not path.is_file():
            raise FileNotFoundError(f"Install pinned SDK: cd {PACKAGE} && npm ci --ignore-scripts")
        versions[name] = json.loads(path.read_text())["version"]
        if versions[name] != "1.3.0":
            raise ValueError("Pi packages must all be pinned at 1.3.0")
    files = [PACKAGE / "package.json", PACKAGE / "package-lock.json", *sorted((PACKAGE / "src").rglob("*.ts")), *sorted((PACKAGE / "prompts").glob("*.md"))]
    hashes = {str(p.relative_to(PACKAGE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    for p in sorted((Path(__file__).parent / "adaptive").glob("*.py")):
        hashes["python/" + p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    for name in ("pi_adaptive.py", "runtime.py", "services.py", "provider_errors.py"):
        hashes["host/" + name] = hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
    return {"version": "1.3.0", "profile": "pi-adaptive-v1", "packages": versions,
        "policy_files_sha256": hashes, "policy_sha256": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()}
