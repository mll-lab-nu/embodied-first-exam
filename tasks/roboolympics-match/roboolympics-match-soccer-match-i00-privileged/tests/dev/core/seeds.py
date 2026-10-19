"""Hidden official seeds (core 0.2.14, docs/framework_zh.md §6.4): a sport frozen for a season plays its official
matches on a seed set that only the organisers hold. The repository has its commitments, never the seeds.

  cells         the set is partitioned by format x level: one cell per format ("duel") or per format and level of a
                format with levels ("match/L1", "match/L2", ...; cell_of); every cell has its own seeds, none shared
  private set   {"schema": PRIVATE, "sport", "created", "cells": {cell: [{"seed": int, "salt": 32 hex}, ...]}}: outside
                git, on the official run host only (tools/seeds.py: $RO_SEEDS_DIR/<sport>.hidden_seeds.json, 0600)
  commitments   one per seed, in cell order: sha256("ro-hidden-seeds/1|<sport>|<seed>|<salt>"); the salt (128 random
                bits) makes a commitment say nothing about its seed
  registration  set_sha256 (the sport and every cell's commitments) and the count per cell: sport.toml
                [official.hidden_seeds] sha256, counts; the commitments are public (sports/<sport>/seed_commitments.json)

At run time the runner hands one seed, its salt and its index to the sim service only (RO_SEED, RO_SEED_SALT,
RO_SEED_INDEX); the players' containers never see them. In such a match the core writes the seed nowhere: the
episode header, final.json, replay_check.json and the broadcast log carry seed -1 and the commitment only
(final.json seed_proof), the sport's own fields and the players' observations and /spec are scrubbed (scrub()), and
the fresh-process replay takes the seed from the same environment and checks it against the commitment. The salt is
never written either (with it, a six-digit seed would follow from its commitment by brute force). The verifier finds
the commitment in the cell of the match's format and level (index()): hidden_seed, hidden_seed_index. The private set
plus the index is the only record of the seed; after the season the set may be published and anyone can recompute
set_sha256 from it.

Standard library only: the generator copies this file next to the verifier (tests/seeds.py)."""
from __future__ import annotations

import hashlib
import re
import secrets

SCHEMA = "ro-hidden-seeds/1"           # the commitment of one seed
SET_SCHEMA = "ro-hidden-seeds/2"       # the registered digest of a partitioned set
PRIVATE = "ro-hidden-seeds-private/2"
PUBLIC = "ro-hidden-seeds-public/2"
SEED_RANGE = (100000, 999999)          # six digits: an int32 for any simulator
HIDDEN = -1                            # the seed as written in the records of a hidden-seed match
HEX = re.compile(r"^[0-9a-f]{64}$")
CELL = re.compile(r"^[a-z0-9][a-z0-9_-]*(/L\d+)?$")    # a format name of sport.toml, "/L<level>"
KEEP = {"step", "k", "steps", "t_sim"}
COMMITMENTS = "seed_commitments.json"  # sports/<sport>/<this>: the public part (public())


def commitment(sport: str, seed: int, salt: str) -> str:
    return hashlib.sha256(f"{SCHEMA}|{sport}|{int(seed)}|{salt}".encode()).hexdigest()


def set_sha256(sport: str, cells: dict) -> str:
    """The registered digest of a seed set: its sport and every cell's commitments, cells in sorted order."""
    text = SET_SCHEMA + "\n" + sport + "\n"
    for c in sorted(cells):
        text += f"[{c}]\n" + "".join(x + "\n" for x in cells[c])
    return hashlib.sha256(text.encode()).hexdigest()


def cell_of(fmt: str, level, cells) -> str | None:
    """The cell of a match: "<format>/L<level>" when the set has it, else "<format>" when it has that, else None."""
    if level is not None and f"{fmt}/L{int(level)}" in cells:
        return f"{fmt}/L{int(level)}"
    return fmt if fmt in cells else None


def new(sport: str, counts: dict, avoid=(), created: str = "") -> dict:
    """A fresh private set: counts = {cell: n}; every seed distinct across cells and none of `avoid`."""
    if not counts or any(int(n) < 1 or not CELL.match(c) for c, n in counts.items()):
        raise ValueError("cells: {\"<format>\" or \"<format>/L<level>\": count >= 1}")
    lo, hi = SEED_RANGE
    used, cells = {int(x) for x in avoid}, {}
    for c in sorted(counts):
        cells[c] = []
        while len(cells[c]) < int(counts[c]):
            s = lo + secrets.randbelow(hi - lo + 1)
            if s not in used:
                used.add(s)
                cells[c].append({"seed": s, "salt": secrets.token_hex(16)})
    return {"schema": PRIVATE, "sport": sport, "created": created, "cells": cells}


def from_seeds(sport: str, cells: dict, created: str = "") -> dict:
    """A private set of given seeds ({cell: [int, ...]}) with fresh salts."""
    out = {c: [{"seed": int(s), "salt": secrets.token_hex(16)} for s in v] for c, v in cells.items()}
    p = {"schema": PRIVATE, "sport": sport, "created": created, "cells": out}
    check_private(p)
    return p


def check_private(p: dict) -> None:
    if p.get("schema") != PRIVATE or not p.get("sport") or not p.get("cells"):
        raise ValueError(f"not a private seed set (schema {PRIVATE}, sport, cells)")
    seen = set()
    for c, entries in p["cells"].items():
        if not CELL.match(c) or not entries:
            raise ValueError(f"bad cell {c!r}")
        for e in entries:
            if not isinstance(e.get("seed"), int) or not re.fullmatch(r"[0-9a-f]{32}", str(e.get("salt", ""))):
                raise ValueError(f"bad entry in {c}: seed int, salt 32 hex")
            if e["seed"] in seen:
                raise ValueError(f"seed {e['seed']} twice (cells never share a seed)")
            seen.add(e["seed"])


def public(p: dict) -> dict:
    """The public part of a private set: what goes into the repository."""
    check_private(p)
    cells = {c: [commitment(p["sport"], e["seed"], e["salt"]) for e in v] for c, v in sorted(p["cells"].items())}
    return {"schema": PUBLIC, "sport": p["sport"], "counts": {c: len(v) for c, v in cells.items()},
            "sha256": set_sha256(p["sport"], cells), "cells": cells}


def registered(sport: str, reg: dict) -> dict:
    """The cells of a registration {sha256, counts, cells}, after checking that they are the registered ones (their
    digest and counts); ValueError otherwise."""
    cells = reg.get("cells") or {}
    counts = reg.get("counts") or {}
    if set(cells) != set(counts) or not cells:
        raise ValueError("hidden seeds: the cells of the commitments and of the counts differ")
    flat = [x for v in cells.values() for x in v]
    if not all(isinstance(x, str) and HEX.match(x) for x in flat) or len(set(flat)) != len(flat):
        raise ValueError("hidden seeds: commitments must be distinct sha256 hex digests")
    for c, v in cells.items():
        if len(v) != int(counts[c]):
            raise ValueError(f"hidden seeds: cell {c} has {len(v)} commitments, count {counts[c]}")
    if set_sha256(sport, cells) != reg.get("sha256"):
        raise ValueError("hidden seeds: the commitments do not hash to the registered sha256")
    return cells


def index(sport: str, fmt: str, level, commit: str | None, reg: dict) -> int | None:
    """The position of a match's commitment in the cell of its format and level, None if it is not there (or the
    registration is inconsistent: then nothing is a member)."""
    if not commit:
        return None
    try:
        cells = registered(sport, reg)
    except (ValueError, TypeError):
        return None
    cell = cell_of(fmt, level, cells)
    if cell is None or commit not in cells[cell]:
        return None
    return cells[cell].index(commit)


def resolve(p: dict, cell: str, i: int, reg: dict | None = None) -> tuple[int, str]:
    """(seed, salt) of entry i of a cell of a private set; with a registration, also checks that the set is the
    registered one."""
    check_private(p)
    if cell not in p["cells"]:
        raise KeyError(f"no cell {cell!r} (cells: {', '.join(sorted(p['cells']))})")
    if not 0 <= i < len(p["cells"][cell]):
        raise IndexError(f"cell {cell} has {len(p['cells'][cell])} seeds (0..{len(p['cells'][cell]) - 1}); asked {i}")
    if reg is not None and public(p)["sha256"] != reg.get("sha256"):
        raise ValueError("this private seed set is not the registered one (sha256 differs)")
    e = p["cells"][cell][i]
    return int(e["seed"]), str(e["salt"])


def scrub(obj, seed: int, salt: str = ""):
    """A copy of obj (JSON-like) without the seed: values under a key named "seed" or "*_seed" become HIDDEN, and so
    does any integer equal to the seed or any string equal to it or to the salt. For a hidden-seed match."""
    seed = int(seed)

    def go(x, key=""):
        if (key == "seed" or key.endswith("_seed")) and not isinstance(x, (dict, list, tuple)):
            return HIDDEN
        if key in KEEP:                       # the core's step counters: never the seed, may reach six digits
            return x
        if isinstance(x, dict):
            return {k: go(v, str(k)) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [go(v) for v in x]
        if isinstance(x, bool):
            return x
        if isinstance(x, int) and x == seed:
            return HIDDEN
        if isinstance(x, float) and x == seed:
            return float(HIDDEN)
        if isinstance(x, str) and (x == str(seed) or (salt and x == salt)):
            return str(HIDDEN)
        return x
    return go(obj)
