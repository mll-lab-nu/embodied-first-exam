#!/usr/bin/env python3
"""Copy the Panda Dynamic Scenes environment package into images/pandadyn/panda_dynamics/, the copy the base image
installs (images/pandadyn/Dockerfile). Run once per source revision; the copy in the repository is then what every task
runs, and its digest is recorded in scripts/pandadyn/instances.json.

    python3 scripts/pandadyn/sync_env.py --src <panda-dynamic-scenes-25 checkout>          # write the copy
    python3 scripts/pandadyn/sync_env.py --src <checkout> --check                          # exit 1 if the copy differs

The copy is the package's simulation code only (scenes, tasks, success predicates, the robot's servo and limits):
the benchmark's own command-line front end (cli.py, which drives its validation tooling) is left out, and so is
everything outside the package (its validation controllers, recorded rollouts, reports and documents). Comments and
configuration keys the code never reads that name that tooling are reworded or dropped (SCRUB, DROP_CONFIG_KEYS): the
agent reads this package in privileged mode, and nothing it reads may point to a solution (docs/PROTOCOL.md §2.7).
Nothing executable changes; ci_checks would not catch a behavioural edit, so SCRUB holds comment and message text only.
"""
from __future__ import annotations
import argparse, hashlib, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEST = ROOT / "images/pandadyn/panda_dynamics"
SKIP = {"cli.py"}
# (file, old, new): each must match exactly once in the source.
SCRUB = [
    ("base_env.py", "reset and event predicates. No witness has permission to mutate scene state.",
     "reset and event predicates. No controller has permission to mutate scene state."),
    ("base_env.py", "# This costs O(elapsed episode steps), and is outside witness stepping.",
     "# This costs O(elapsed episode steps), and is outside controller stepping."),
    ("props/primitives.py", '"""Reset-only utility. Never call this from task update or witness code."""',
     '"""Reset-only utility. Never call this from task update or controller code."""'),
    ("manifest.py", "Presence here is a design/registration fact, never a feasibility claim. Current\n"
                    "full-episode evidence is stored separately in reports/acceptance.json.\n",
     "Presence here is a design/registration fact, never a feasibility claim.\n"),
    ("manifest.py", 'f"Unknown canonical task {value!r}. Use scripts/list_tasks.py; legacy IDs are archived (docs/MIGRATION_V4.md)."',
     'f"Unknown canonical task {value!r}."'),
    ("tasks/single/load_switch_recover.py", '# v5: declared seeded instance variation (config "randomization"):',
     "# v5: declared seeded instance variation:"),
]
DROP_CONFIG_KEYS = ("status", "randomization")     # never read (config.py reads common / difficulty / ranges)
FORBIDDEN = re.compile(r"witness|validation|reports/|scripts/|artifacts|docs/|acceptance|calibrat|oracle|\bsolution", re.I)


def planned(src: pathlib.Path) -> dict[str, bytes]:
    pkg = src / "panda_dynamics"
    out: dict[str, bytes] = {}
    for p in sorted(pkg.rglob("*")):
        rel = p.relative_to(pkg).as_posix()
        if not p.is_file() or "__pycache__" in p.parts or rel in SKIP:
            continue
        if p.suffix == ".py":
            out[rel] = p.read_bytes()
        elif p.suffix == ".json" and rel.startswith("configs/"):
            d = json.loads(p.read_text())
            for k in DROP_CONFIG_KEYS:
                d.pop(k, None)
            out[rel] = (json.dumps(d, indent=2, ensure_ascii=False) + "\n").encode()
    for rel, old, new in SCRUB:
        text = out[rel].decode()
        if text.count(old) != 1:
            raise SystemExit(f"SCRUB {rel}: expected exactly one match of {old[:60]!r}, found {text.count(old)}")
        out[rel] = text.replace(old, new).encode()
    bad = [(rel, m.group(0)) for rel, b in out.items() for m in FORBIDDEN.finditer(b.decode())]
    if bad:
        raise SystemExit(f"pointer-like text left in the copy: {bad[:10]}")
    return out


def digest(files: dict[str, bytes]) -> str:
    return hashlib.sha256(b"".join(k.encode() + b"\0" + v + b"\0" for k, v in sorted(files.items()))).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    files = planned(pathlib.Path(a.src))
    have = {p.relative_to(DEST).as_posix(): p.read_bytes() for p in DEST.rglob("*") if p.is_file()} if DEST.exists() else {}
    diffs = sorted(set(have) ^ set(files)) + sorted(k for k in files if k in have and have[k] != files[k])
    if a.check:
        print("\n".join(diffs) or "identical"); return 1 if diffs else 0
    for k in set(have) - set(files):
        (DEST / k).unlink()
    for k, v in files.items():
        p = DEST / k; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(v)
    print(f"wrote {len(files)} files to {DEST.relative_to(ROOT)} (digest {digest(files)[:16]}; {len(diffs)} changed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
