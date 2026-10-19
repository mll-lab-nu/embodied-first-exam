"""Identity of a request variant and its freshly executed family controls."""
from __future__ import annotations


def normalize(value):
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("request variant must be a string or None")
    return value


def scope(family, variant):
    variant = normalize(variant)
    members = [m for m in family.members if variant in family.variants(m)] if variant else []
    if variant and not members:
        raise ValueError(f"{family.id}: no request variant {variant!r}")
    return {"schema": 1, "variant_members": members,
            "control_members": [m for m in family.members if m not in members]}


def key_identity(key):
    return (key.get("family"), key.get("member"), key.get("robot"), key.get("seed"),
            key.get("interface", "skill"), key.get("cameras"), key.get("movers", "scripted"),
            key.get("clock", "paused"), key.get("evidence"), normalize(key.get("variant")))


def reference_keys(family, variant, robot, interface, seeds, cameras, movers="scripted", clock="paused"):
    eligible = scope(family, variant)["variant_members"]
    return [{"family": family.id, "member": m, "robot": robot, "seed": seed,
             "interface": interface, "cameras": cam, "movers": movers, "clock": clock,
             "evidence": level, "variant": variant if m in eligible else None}
            for cam in cameras for seed in seeds for m in family.members
            for level in (family.evidence_levels(m) or (None,))]
