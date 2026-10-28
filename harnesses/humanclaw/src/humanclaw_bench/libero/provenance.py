"""Reproducible code/configuration records, excluding credentials and datasets."""
import hashlib
import json
import os
import math
from pathlib import Path
import platform
import subprocess

from .protocol import digest


def file_hash(path):
    """Compute a file digest without loading the entire artifact into memory."""
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def framework_identity():
    """Record actual framework source hashes and runtime identity."""
    root = Path(__file__).resolve().parents[3]
    files = {str(p.relative_to(root)): file_hash(p)
             for p in sorted((root / "src" / "humanclaw_bench").rglob("*.py"))}
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root,
                                         stderr=subprocess.DEVNULL, text=True).strip()
    except subprocess.SubprocessError:
        commit = (root / "UPSTREAM_COMMIT").read_text().strip() if (root / "UPSTREAM_COMMIT").exists() else None
    return {"git_base": commit, "actual_source_sha256": digest(files), "files": files,
            "python": platform.python_version(), "platform": platform.platform()}


def assets_identity():
    # A deployment manifest freezes downloaded revisions. Per-task exact BDDL
    # and init-state hashes are captured separately by the environment owner.
    """Read pinned deployment assets and shared-service startup evidence."""
    path = os.environ.get("LIBERO_ASSETS_MANIFEST")
    result = json.loads(Path(path).read_text()) if path else {"manifest": "not_configured"}
    shared = os.environ.get("LIBERO_SHARED_SERVICE_MANIFEST")
    if shared:
        result["shared_service_startup"] = json.loads(Path(shared).read_text())
    return result


OBSERVABILITY = {
    "model_http": {"coverage": "all requests using the session proxy", "includes": [
        "streaming/nonstreaming Responses", "Chat Completions", "compaction", "SDK retries",
        "Planner/Engineer/Reviewer", "tool-internal VLM requests"],
        "missing_usage": "unknown; never imputed as zero", "billing": "explicit rate card only"},
    "environment_tools": "durable dispatch journal, args/results/images, actual 8D control steps",
    "native_modules": "only public App Server/RPC events; unexposed internals are not inferred",
    "roborsi_modules": "role entry/exit, dispatch/subtools, selected perception/solver/motion function boundaries",
    "gpu_perception_cost": "wall-clock module spans; no invented token charge or GPU dollar rate",
    "private_evaluator": "separate final simulator verdict, unavailable to acting agents",
    "native_raw": "raw commands/events/stderr in unified event stream, plus native home/session files",
    "roborsi_raw": "upstream workspace/trace files beneath the fresh per-run roborsi_home",
}


def validate_pricing(pricing):
    """Require explicit, versioned and finite provider rate-card values."""
    if pricing is None:
        return
    if not isinstance(pricing, dict):
        raise ValueError("Pricing must be an explicit object")
    models = pricing.get("models")
    entries = models.items() if isinstance(models, dict) else [(pricing.get("model"), pricing)]
    for model, rate in entries:
        if not model or not all(rate.get(k) for k in ("provider", "date", "version")) or rate.get("currency") != "USD":
            raise ValueError("Each rate card requires model, provider, date, version and USD currency")
        for key in ("input_per_million", "cached_input_per_million", "output_per_million"):
            value = rate.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(f"Invalid explicit price: {key}")
