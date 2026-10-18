"""The toolkit manifest (docs/framework_zh.md §6.3.5, §9 robot and mode rule 3): what a mode gives the players of one
sport x assembled configuration, as a public, versioned file of the sport (sports/<sport>/seat/toolkit.toml; it
belongs to the sport, not to the robot). Standard library only.

    [toolkit]   id, version, sport, level ("low" | "high"), configuration (the assembled configuration of
                bodies/assembly.py, or the sport's declared machine), definition (optional)
    [[tools]]   name, kind (model | library | policy | controller | interface | data), api (what it offers),
                file (where the seat has it) + source (path in sports/<sport>/) + sha256 for every kind but
                interface; version for library / policy / controller; license (optional), notes
    [limits]    source (where the real limits come from: bodies/<robot>/body.toml, or the machine's ranges) and
                enforced_by (bodies/servo.py, bodies/limits.py, or the sport's command schema for a machine)
    [forbidden] skills (the sport's core skills: never given at this level), modules (sport files the seat never
                gets: the platform's implementation), develop (what the player develops)
    [boundary]  baseline (a skill directory: the simplest implementation from these tools alone) and threshold
                (its API-test success rate must stay at or below it; rule 5). Level low only.

sha256 of a file is its bytes'; of a directory, sha256 over its sorted "relative/path\\0<file sha256>\\n" lines
(__pycache__ and *.pyc skipped). Changing the toolkit changes the task: bump [toolkit] version and the sport's
revision, re-run the reference and boundary evaluations (tools/check SPORT --stages 6).

    python3 -m skilleval.toolkit check sports/<sport>/seat/toolkit.toml [--fix]
"""

from __future__ import annotations

import hashlib
import re
import sys
import tomllib
from pathlib import Path

KINDS = {"model", "library", "policy", "controller", "interface", "data"}
VERSIONED = {"library", "policy", "controller"}
NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def sport_dir_of(manifest: Path) -> Path:
    for p in Path(manifest).resolve().parents:
        if (p / "sport.toml").is_file():
            return p
    raise FileNotFoundError(f"no sport.toml above {manifest}")


def digest(path: Path) -> str:
    path = Path(path)
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    lines = []
    for f in sorted(path.rglob("*")):
        if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc":
            lines.append(f"{f.relative_to(path).as_posix()}\0{hashlib.sha256(f.read_bytes()).hexdigest()}\n")
    return hashlib.sha256("".join(lines).encode()).hexdigest()


def load(manifest) -> dict:
    return tomllib.loads(Path(manifest).read_text())


def problems(manifest, sport: str | None = None, level: str | None = None) -> list[str]:
    """Schema and sha256 problems of a manifest (empty: fine)."""
    manifest = Path(manifest)
    try:
        m = load(manifest)
    except Exception as e:  # noqa: BLE001
        return [f"{manifest.name}: {e}"]
    root = sport_dir_of(manifest)
    bad = []
    tk = m.get("toolkit") or {}
    for k in ("id", "version", "sport", "level", "configuration"):
        if not tk.get(k):
            bad.append(f"[toolkit] {k} missing")
    if sport and tk.get("sport") != sport:
        bad.append(f"[toolkit] sport = {tk.get('sport')!r}, not {sport!r}")
    if tk.get("level") not in ("low", "high") or (level and tk.get("level") != level):
        bad.append(f"[toolkit] level = {tk.get('level')!r}" + (f", not {level!r}" if level else ""))
    tools = m.get("tools") or []
    if not tools:
        bad.append("[[tools]]: none (a level gives at least its command interface)")
    names = [t.get("name") for t in tools]
    if len(set(names)) != len(names):
        bad.append("[[tools]] names are not unique")
    for t in tools:
        n = t.get("name", "?")
        if not NAME.match(str(n)):
            bad.append(f"tool {n!r}: name must be lower_case")
        if t.get("kind") not in KINDS:
            bad.append(f"tool {n}: kind {t.get('kind')!r} not in {sorted(KINDS)}")
        if not t.get("api"):
            bad.append(f"tool {n}: api (what it offers) missing")
        if t.get("kind") == "interface":
            continue
        if not (str(t.get("file", "")).startswith("/") and t.get("source") and t.get("sha256")):
            bad.append(f"tool {n}: file (absolute seat path), source and sha256 needed")
            continue
        if t.get("kind") in VERSIONED and not t.get("version"):
            bad.append(f"tool {n}: version needed for a {t['kind']}")
        src = root / t["source"]
        if not src.exists():
            bad.append(f"tool {n}: source {t['source']} missing")
        elif digest(src) != t["sha256"]:
            bad.append(f"tool {n}: sha256 of {t['source']} is {digest(src)}, the manifest says {t['sha256']}")
    lim = m.get("limits") or {}
    for k in ("source", "enforced_by"):
        if not lim.get(k):
            bad.append(f"[limits] {k} missing (B0: every level keeps the real limits)")
    fb = m.get("forbidden") or {}
    if tk.get("level") == "low":
        if not fb.get("skills"):
            bad.append("[forbidden] skills missing: the sport's core skills a low-level player develops itself")
        if not fb.get("develop"):
            bad.append("[forbidden] develop missing: what the player develops")
        for f in fb.get("modules", []):
            if not (root / f).exists():
                bad.append(f"[forbidden] module {f} does not exist in the sport")
        bd = m.get("boundary") or {}
        th = bd.get("threshold")
        if not bd.get("baseline") or not isinstance(th, (int, float)) or not 0 <= th <= 1:
            bad.append("[boundary] baseline and threshold (0..1) needed at the low level (rule 5)")
        elif not (root / bd["baseline"]).is_dir():
            bad.append(f"[boundary] baseline {bd['baseline']} is not a directory of the sport")
    return bad


def fix(manifest) -> list[str]:
    """Rewrite the sha256 of every [[tools]] entry with a source; returns what changed."""
    manifest = Path(manifest)
    root = sport_dir_of(manifest)
    m = load(manifest)
    want = {
        t["name"]: digest(root / t["source"])
        for t in m.get("tools", [])
        if t.get("source") and (root / t["source"]).exists()
    }
    out, name, changed = [], None, []
    for line in manifest.read_text().splitlines(keepends=True):
        s = line.strip()
        if s.startswith("["):
            name = None
        mm = re.match(r'name\s*=\s*"([^"]+)"', s)
        if mm:
            name = mm.group(1)
        mh = re.match(r'(\s*sha256\s*=\s*")([0-9a-f]*)(".*)', line, re.S)
        if mh and name in want and mh.group(2) != want[name]:
            line = mh.group(1) + want[name] + mh.group(3)
            changed.append(name)
        out.append(line)
    manifest.write_text("".join(out))
    return changed


def main(argv):
    if len(argv) < 2 or argv[0] != "check":
        print(__doc__.strip().splitlines()[-1].strip())
        return 2
    if "--fix" in argv:
        print("updated:", fix(argv[1]) or "nothing")
    bad = problems(argv[1])
    for b in bad:
        print("FAIL", b)
    print(f"{argv[1]}: {'ok' if not bad else f'{len(bad)} problem(s)'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
