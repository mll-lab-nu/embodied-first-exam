"""Readings that only legacy tasks (ro-taskspec/1, tests/contract.json from sport.toml) need: the official
configuration of the core 0.2/0.3 verifier (core/grading.py official, hidden_index; unchanged), kept so the
projected reward.json keeps its `official_config` / `hidden_seed` fields until the sports move to Task releases.
In the new framework official eligibility is the verdict's `official` (frozen release, official Fixture, hidden seed,
certified backend, no override)."""
from __future__ import annotations

try:                                         # the verifier's copy next to the package (tests/eo_judge/seeds.py)
    from . import seeds as seedset           # type: ignore
except ImportError:
    try:
        from core import seeds as seedset    # the repository
    except ImportError:                      # pragma: no cover
        seedset = None


def run_hook(path, world: dict) -> dict:
    """The sport's scoring hook (a legacy task's sport_grade.py: evaluate(final) -> numbers), loaded and run without
    writing bytecode anywhere: judging never changes the evidence it reads (a sealed Run directory's task/ stays as
    it was sealed, so its digests still hold)."""
    import importlib.util
    import sys
    old = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location("sport_grade", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.evaluate(world)
    finally:
        sys.dont_write_bytecode = old


def hidden_index(d: dict, contract: dict) -> int | None:
    """The match seed's position in its cell of the sport's registered hidden seed set (core/seeds.py): the
    commitment the match service recorded must be one of that cell's. None if it is not one."""
    reg = (contract.get("official") or {}).get("hidden_seeds")
    proof = d.get("seed_proof") or {}
    if not reg or seedset is None:
        return None
    return seedset.index(contract.get("sport", ""), d.get("format") or "", (d.get("cfg") or {}).get("level"),
                         proof.get("commitment"), reg)


def official(d: dict, contract: dict) -> bool:
    """An official configuration: the seed (a registered hidden seed once the sport has a hidden set, else one of the
    public [official] seeds), the slowdown, the first player and the level (core/grading.py, unchanged)."""
    off = contract.get("official", {})
    if ((contract.get("formats") or {}).get(d.get("format") or "") or {}).get("preview"):
        return False
    ok = True
    if off.get("hidden_seeds"):
        ok &= hidden_index(d, contract) is not None
    elif "seeds" in off:
        ok &= int(d.get("seed") or 0) in off["seeds"]
    if "slowdowns" in off:
        ok &= float(d.get("slowdown") or 0) in off["slowdowns"].get(d.get("play", "program"), [])
    if off.get("first_any"):
        ok &= d.get("first") in (d.get("cfg") or {}).get("seats", []) or d.get("first") in (d.get("sides") or {}).values()
    if "levels" in off and (d.get("cfg") or {}).get("level") is not None:
        ok &= int(d["cfg"]["level"]) in off["levels"]
    return bool(ok)


def line_ok(score, line: dict) -> bool:
    if "score_at_least" in line:
        return score >= line["score_at_least"]
    if "score_at_most" in line:
        return score <= line["score_at_most"]
    return False


def official_reading(d: dict, contract: dict, sport_fields: dict | None) -> dict:
    """{"official_config", "hidden_seed_index"} as the legacy verifier computed them: the core's rule, the sport's
    own value (its scoring hook may replace it), a runtime override makes it 0, a registered hidden set requires a
    registered hidden seed."""
    hidx = hidden_index(d, contract)
    oc = int(official(d, contract))
    if sport_fields and "official_config" in sport_fields:
        oc = int(sport_fields["official_config"])
    if (d.get("taskspec") or {}).get("overrides"):
        oc = 0
    if (contract.get("official") or {}).get("hidden_seeds"):
        oc = int(oc == 1 and hidx is not None)
    return {"official_config": oc, "hidden_seed_index": hidx}
