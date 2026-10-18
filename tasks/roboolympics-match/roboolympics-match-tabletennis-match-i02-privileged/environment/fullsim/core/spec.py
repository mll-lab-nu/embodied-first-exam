"""The sport's declarations (sport.toml next to its plugin.py, docs/framework_zh.md §4.2): data, read by the core
(observation whitelist, team channel, success line, timing), the generator, the checks and the documentation."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path


def load(plugin_path: str | os.PathLike) -> dict:
    p = Path(plugin_path)
    p = p / "sport.toml" if p.is_dir() else p.with_name("sport.toml")
    if not p.exists():
        return {}
    return tomllib.loads(p.read_text())


def whitelist(decl: dict) -> set[str] | None:
    fields = (decl.get("observation") or {}).get("fields")
    return set(fields) if fields is not None else None


def reaction_delay(decl: dict) -> int:
    """sport.toml [timing] reaction_delay_steps (core 0.2.18): the sport's declared reaction delay D in control
    steps, the same for every seat. In real time an act takes effect at step max(the next control-step boundary, s + D),
    where s is the step of the latest world state the service sent to the seat (any reply's `now`); the act is
    lowered at that step. The screening harness (tools/screen/play.py) plays with the same D. Not declared: 0, every
    act takes effect at the next control-step boundary (the rule before 0.2.18)."""
    v = (decl.get("timing") or {}).get("reaction_delay_steps", 0)
    if isinstance(v, bool) or not isinstance(v, int) or v < 0:
        raise ValueError(f"[timing] reaction_delay_steps must be an integer >= 0 (control steps), not {v!r}")
    return v
