"""Strict per-task JSON configuration, SI units. Unknown overrides are errors."""

from pathlib import Path
import json

CONFIG_DIR = Path(__file__).parent / "configs"


def load_config(task: str, difficulty: str, overrides=None) -> dict:
    if difficulty not in ("debug", "nominal", "hard"):
        raise ValueError("difficulty must be debug, nominal or hard")
    path = CONFIG_DIR / f"{task}.json"
    data = json.loads(path.read_text())
    resolved = data["common"] | data["difficulty"][difficulty]
    for key, value in (overrides or {}).items():
        if key not in resolved:
            raise ValueError(f"Unknown parameter {key}; allowed: {sorted(resolved)}")
        resolved[key] = value
    for key, bounds in data.get("ranges", {}).items():
        if not bounds[0] <= resolved[key] <= bounds[1]:
            raise ValueError(f"{key} must be within {bounds}, got {resolved[key]}")
    if resolved["horizon"] <= 0 or resolved["object_mass"] <= 0:
        raise ValueError("horizon and object_mass must be positive")
    return resolved
