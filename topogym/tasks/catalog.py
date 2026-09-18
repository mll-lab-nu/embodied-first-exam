"""Read and validate baseline cards without importing a physics backend.

Cards describe proposed environments. A valid card is not physics evidence.
The first version freezes baselines; candidate axes are never sampled here.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

CARD_ROOT = Path(__file__).resolve().parents[2] / "configs" / "task_cards"
TASK_IDS = (
    "interlocked_claws", "rope_threading", "lock_picking", "hedgehog_in_cage",
    "fiber_bundling", "horseshoe_ring", "knot_untying", "cast_coil",
    "cast_keyhole", "buzz_wire_3d",
)


def _lookup(data, path):
    for key in path.split("."):
        data = data[key]
    return data


def validate_card(card):
    required = {"schema_version", "task_id", "baseline", "axes", "assets",
                "physics", "initialization", "robot", "rejection_rules", "first_probe"}
    if missing := required - card.keys():
        raise ValueError(f"Missing card fields: {sorted(missing)}")
    if card["schema_version"] != 1 or card["task_id"] not in TASK_IDS:
        raise ValueError("Unknown task or card schema")
    if not card["rejection_rules"] or not card["first_probe"]:
        raise ValueError("A card must declare rejection rules and a first probe")
    if card["physics"].get("qualification") != "unqualified":
        raise ValueError("Baseline proposals cannot claim physical qualification")
    names = set()
    for axis in card["axes"]:
        path = axis["path"]
        if path in names or not axis.get("unit"):
            raise ValueError(f"Duplicate axis or missing unit: {path}")
        names.add(path)
        try:
            _lookup(card["baseline"], path)
        except (KeyError, TypeError) as exc:
            raise ValueError(f"Axis {path} has no baseline value") from exc
        if axis.get("status") != "candidate":
            raise ValueError("Unqualified axes must remain candidate")
    def finite(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Non-finite card parameter")
        if isinstance(value, dict):
            for v in value.values(): finite(v)
        elif isinstance(value, list):
            for v in value: finite(v)
    finite(card)
    for asset in card["assets"]:
        if asset["status"] == "local_source":
            p = CARD_ROOT.parents[1] / asset["location"]
            if not p.is_file():
                raise ValueError(f"Missing local source: {p}")
    return card


def load_card(task_id):
    if task_id not in TASK_IDS:
        raise ValueError(f"Unknown task: {task_id}")
    import yaml
    card = yaml.safe_load((CARD_ROOT / f"{task_id}.yaml").read_text())
    if card.get("task_id") != task_id:
        raise ValueError("Card identity differs from filename")
    return validate_card(card)


def baseline_manifest(task_id, seed=0):
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    card = load_card(task_id)
    payload = json.dumps(card, sort_keys=True, ensure_ascii=False, allow_nan=False)
    return {"schema_version": 1, "task_id": task_id, "seed": seed,
            "sampling": "fixed_baseline", "physics_qualified": False,
            "card_sha256": hashlib.sha256(payload.encode()).hexdigest(),
            "card": deepcopy(card)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = {"card_count": len(TASK_IDS), "validation": "schema_and_sources_only",
              "baselines": [baseline_manifest(name) for name in TASK_IDS]}
    data = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(data)
        print(f"Validated {len(TASK_IDS)} baseline cards: {args.output}")
    else:
        print(data, end="")


if __name__ == "__main__":
    main()
