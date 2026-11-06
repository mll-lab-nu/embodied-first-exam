"""API-test requests: hidden on the simulator side, a public practice subset for the seat (docs/framework_zh.md
§6.3.7: "隐藏请求只在赛后使用"). Standard library only.

A case is one JSON line {"id", "request": {field: value}, ...}: whatever else the sport's evaluator hook needs to run
it (a start state, the reference's result) stays in the case. The sport builds its cases (e.g. from its reference
player's matches, kept only if feasible under the real limits), then:

    public, hidden = split(cases, share=0.3)          # by a hash of the id: stable, no seed to guess
    write(sport_dir / "lowlevel/cases/hidden.jsonl", hidden)
    write(sport_dir / "lowlevel/cases/public.jsonl", [practice_view(c) for c in public])

sport.toml [modes.low.cases] names both files and the seat path of the public one; [seat.low] files ships the public
file to the seat; the hidden file never leaves the simulator side: tools/sportlib.assemble_sim leaves it out of the
generated task (only the checks and the evaluator get it) and skilleval/declare.py fails a seat that would ship it.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

PRACTICE_KEYS = ("id", "request", "state", "reference")  # what the public practice view may hold


def load(path) -> list[dict]:
    p = Path(path)
    raw = gzip.decompress(p.read_bytes()).decode() if p.suffix == ".gz" else p.read_text()
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def write(path, rows) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in rows)
    p.write_bytes(gzip.compress(text.encode(), mtime=0) if p.suffix == ".gz" else text.encode())
    return p


def bucket(case_id: str, salt: str = "") -> float:
    """[0, 1) from the id's sha256 (stable across machines and Python versions)."""
    return int(hashlib.sha256((salt + str(case_id)).encode()).hexdigest()[:8], 16) / 16**8


def split(cases: list[dict], share: float = 0.3, salt: str = "") -> tuple[list[dict], list[dict]]:
    """(public, hidden): a case is public iff bucket(id) < share."""
    pub = [c for c in cases if bucket(c["id"], salt) < share]
    return pub, [c for c in cases if bucket(c["id"], salt) >= share]


def practice_view(case: dict, keys=PRACTICE_KEYS) -> dict:
    """What the seat may see of a public case (no simulator state, no seed)."""
    return {k: case[k] for k in keys if k in case}


def problems(hidden: list[dict], public: list[dict], contract=None) -> list[str]:
    """Hidden and public are disjoint, ids unique, the public view holds only PRACTICE_KEYS, and (with a contract)
    every request is valid."""
    bad = []
    ids_h, ids_p = [c.get("id") for c in hidden], [c.get("id") for c in public]
    if len(set(ids_h)) != len(ids_h) or len(set(ids_p)) != len(ids_p):
        bad.append("case ids are not unique")
    if set(ids_h) & set(ids_p):
        bad.append(f"{len(set(ids_h) & set(ids_p))} case(s) both hidden and public")
    extra = sorted({k for c in public for k in c} - set(PRACTICE_KEYS))
    if extra:
        bad.append(f"the public practice file holds {extra} (only {list(PRACTICE_KEYS)})")
    if not hidden:
        bad.append("no hidden case")
    if contract is not None:
        for c in hidden + public:
            why = contract.valid_request(c.get("request"))
            if why:
                bad.append(f"case {c.get('id')}: {why}")
                break
    return bad
