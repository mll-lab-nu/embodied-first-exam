#!/usr/bin/env python3
"""Generate RoboPaint-strict: tasks/robopaint-strict-<family>-<target>-i00-{privileged,standard} from the committed RoboPaint pairs
tasks/robopaint-<family>-<target>-i00-{privileged,standard} (docs/benchmarks/robopaint-strict.md).

    python3 scripts/robopaint_strict/mk_tasks.py                          # (re)write every strict pair; `git diff tasks/` stays empty
    python3 scripts/robopaint_strict/mk_tasks.py --check                  # write nothing; exit 1 if a task dir differs
    python3 scripts/robopaint_strict/mk_tasks.py robopaint-kaishu-yong-i00 # these pairs only
Needs only Python 3 (no simulator). Then `cd tasks && harbor add --scan .` when a digest changed.

A strict pair is its RoboPaint pair (same scene, frozen instance, picture, tooling, picture rule and reference solution) with the
process rules added:
  - every copy of the frozen instance gets the rules in target.success: max_path_mm everywhere; calligraphy and lettering
    min_mark_width_mm (colouring in = a longer path of thinner marks); paintings max_scribble, max_scribble_share,
    scribble_min_mm (sweeps). rules.json holds the family parameters and, per pair, the reference solution's path and mark width
    on the main sheet (reference_path_mm, reference_mark_width_mm, measured by measure_reference.py in the base image);
    max_path_mm = path_factor x that path rounded up to round_mm, min_mark_width_mm = mark_factor x that width rounded down to
    0.01 mm. The scene and its hash (instance_sha) do not change;
  - rcb_brush_strict.py (graders' side only: tests/, environment/scorer/, environment/sim/) applies them: the verifier replays
    with it (tests/grade.py, tests/Dockerfile), the privileged scoring service imports it (RCB_TOOL_MODULE) and the standard
    collect hook replays with it (RCB_TOOL);
  - the texts: the rules from texts/rules_<group>_<mode>.md in instruction.md (after "Target and score"), texts/readme_<mode>.md
    in README.md, a sentence in the task.toml description; the benchmark name RoboPaint-strict, the family
    robopaint_strict_<family>_<target>, the keyword robopaint-strict, the oracle evidence (rules.json).
Every task ends with scripts/task_conventions.py's normalize(); a task dir holds exactly what the generator writes.
"""

from __future__ import annotations
import argparse, json, math, os, pathlib, re, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = ROOT / "scripts" / "robopaint_strict"
MODULE = "rcb_brush_strict.py"
GROUP = {
    "kaishu": "calligraphy",
    "xingshu": "calligraphy",
    "lettering": "lettering",
    "acrylic": "painting",
    "oil": "painting",
}
SRC_RE = re.compile(r"^robopaint-(kaishu|xingshu|lettering|acrylic|oil)-([a-z0-9]+(?:-[a-z0-9]+)*)-i00$")


def render(t: str, v: dict) -> str:
    for k, x in v.items():
        t = t.replace("{{" + k + "}}", str(x))
    left = re.findall(r"\{\{[A-Z_]+\}\}", t)
    if left:
        raise SystemExit(f"unfilled placeholders {sorted(set(left))}")
    return t


def fmt(x: float) -> str:
    return f"{x:g}"


def rules_for(base: str, cfg: dict) -> tuple[dict, dict]:
    """(the rule keys added to target.success, the text values) of a RoboPaint pair <base>."""
    fam = SRC_RE.match(base).group(1)
    F = cfg["families"][fam]
    ref = float(cfg["reference_path_mm"][base])
    step = float(F["round_mm"])
    budget = math.ceil(F["path_factor"] * ref / step - 1e-9) * step
    rule = {"max_path_mm": float(budget)}
    v_mark = {}
    if "mark_factor" in F:  # calligraphy, lettering: colouring in = a long path AND thin marks
        ref_w = float(cfg["reference_mark_width_mm"][base])
        min_w = math.floor(F["mark_factor"] * ref_w / 0.01 + 1e-9) * 0.01
        rule["min_mark_width_mm"] = round(min_w, 2)
        v_mark = {
            "MIN_MARK_WIDTH_MM": f"{min_w:.2f}",
            "REF_MARK_WIDTH_MM": f"{ref_w:.2f}",
            "MARK_FACTOR": fmt(F["mark_factor"]),
            "EVIDENCE": f"path_mm {ref:.0f} and mark_width_mm {ref_w:.2f}, against the colouring-in limits {fmt(budget)} mm and "
            f"{min_w:.2f} mm",
        }
    if "max_scribble" in F:
        rule.update(
            {
                "max_scribble": float(F["max_scribble"]),
                "max_scribble_share": float(F["max_scribble_share"]),
                "scribble_min_mm": float(F["scribble_min_mm"]),
            }
        )
    v = {
        "MAX_PATH_MM": fmt(budget),
        "REF_PATH_MM": f"{ref:.0f}",
        "PATH_FACTOR": fmt(F["path_factor"]),
        "MAX_SCRIBBLE": fmt(F.get("max_scribble", 0)),
        "MAX_SCRIBBLE_SHARE": fmt(F.get("max_scribble_share", 0)),
        "SCRIBBLE_SHARE_PCT": fmt(100 * F.get("max_scribble_share", 0)),
        "SCRIBBLE_MIN_MM": fmt(F.get("scribble_min_mm", 0)),
        "SRC": base,
        "EVIDENCE": f"path_mm {ref:.0f} of the {fmt(budget)} mm budget; its strokes are sweeps",
        **v_mark,
    }
    return rule, v


def add_rule(raw: bytes, rule: dict) -> bytes:
    """An instance.json (indent=1, ensure_ascii=False, no trailing newline, as rcb_brush_score writes it) with the rules added at
    the end of target.success."""
    d = json.loads(raw.decode("utf-8"))
    if json.dumps(d, indent=1, ensure_ascii=False).encode("utf-8") != raw:
        raise SystemExit("an instance.json is not in rcb_brush_score's format (indent=1, ensure_ascii=False)")
    d["target"]["success"].update(rule)
    return json.dumps(d, indent=1, ensure_ascii=False).encode("utf-8")


def sub1(s: str, old: str, new: str, where: str) -> str:
    if s.count(old) != 1:
        raise SystemExit(f"{where}: expected exactly one {old!r} ({s.count(old)} found)")
    return s.replace(old, new)


def plan_pair(base: str, cfg: dict) -> dict:
    """{task dir name: {rel path: (bytes, mode)}} for both strict twins of the RoboPaint pair <base>."""
    fam, slug = SRC_RE.match(base).groups()
    rule, v = rules_for(base, cfg)
    module = (HERE / MODULE).read_bytes()
    texts = {p.name: p.read_text(encoding="utf-8") for p in (HERE / "texts").glob("*.md")}
    out = {}
    for mode in ("privileged", "standard"):
        src = ROOT / "tasks" / f"{base}-{mode}"
        if not (src / "task.toml").is_file():
            raise SystemExit(f"{src}: missing (the RoboPaint pair is the source of the strict pair)")
        name = f"robopaint-strict-{fam}-{slug}-i00-{mode}"
        files = {
            p.relative_to(src).as_posix(): [p.read_bytes(), 0o755 if p.stat().st_mode & 0o100 else 0o644]
            for p in sorted(src.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts
        }
        for rel in list(files):
            if rel.endswith("instance.json"):
                files[rel][0] = add_rule(files[rel][0], rule)
        if mode == "privileged":
            files["tests/" + MODULE] = [module, 0o644]
            files["environment/scorer/" + MODULE] = [module, 0o644]
            g = files["tests/grade.py"][0].decode()
            g = sub1(
                g,
                'tool = os.path.join(here, "rcb_brush.py")',
                f'tool = os.path.join(here, "{MODULE}")   # RoboPaint-strict: the picture rule + the process rules',
                "tests/grade.py",
            )
            files["tests/grade.py"][0] = g.encode()
            df = files["tests/Dockerfile"][0].decode()
            df = sub1(df, " rcb_brush_score.py ", f" rcb_brush_score.py {MODULE} ", "tests/Dockerfile")
            files["tests/Dockerfile"][0] = df.encode()
            dc = files["environment/docker-compose.yaml"][0].decode()
            dc = sub1(
                dc,
                "RCB_TOOL_MODULE: rcb_brush\n",
                "RCB_TOOL_MODULE: rcb_brush_strict   # the scores with the process rules (rcb_brush_strict.py)\n",
                "environment/docker-compose.yaml",
            )
            files["environment/docker-compose.yaml"][0] = dc.encode()
        else:
            files["environment/sim/" + MODULE] = [module, 0o644]
            dc = files["environment/docker-compose.yaml"][0].decode()
            dc = sub1(
                dc,
                "RCB_TOOL: /srv/rcb_brush.py\n",
                f"RCB_TOOL: /srv/{MODULE}   # the collect hook's replays score with the process rules\n",
                "environment/docker-compose.yaml",
            )
            files["environment/docker-compose.yaml"][0] = dc.encode()
        # texts
        ins = files["instruction.md"][0].decode()
        ins = re.sub(r"\A# RoboPaint · ", "# RoboPaint-strict · ", ins)
        if not ins.startswith("# RoboPaint-strict · "):
            raise SystemExit(f"{src}/instruction.md: unexpected title")
        block = render(texts[f"rules_{GROUP[fam]}_{mode}.md"], v).rstrip() + "\n\n"
        m = re.search(r"^## Target and score\n.*?(?=^## )", ins, re.S | re.M)
        if not m:
            raise SystemExit(f"{src}/instruction.md: no '## Target and score' section")
        ins = ins[: m.end()] + block + ins[m.end() :]
        files["instruction.md"][0] = ins.encode()
        rd = files["README.md"][0].decode()
        for m_ in ("privileged", "standard"):  # the twin is the strict twin
            rd = rd.replace(f"`{base}-{m_}`", f"`robopaint-strict-{fam}-{slug}-i00-{m_}`")
        if mode == "privileged":
            rd = sub1(
                rd,
                "Oracle label `partial`: the recorded oracle runs predate this version's files (task.toml `oracle_evidence`); human "
                "review in PR #3.",
                "Oracle label `partial`: the RoboPaint pair's reference solution, scored under the process rules "
                "(task.toml `oracle_evidence`).",
                "README.md",
            )
        else:
            rd = sub1(
                rd,
                "label `partial` (task.toml `oracle_evidence`: the recorded runs predate this version), human review in PR #3.",
                "label `partial` (task.toml `oracle_evidence`: the RoboPaint pair's reference solution, scored under the process rules).",
                "README.md",
            )
        rd = sub1(
            rd,
            "\n## Verification\n",
            "\n## Verification\n" + texts[f"readme_verification_{mode}.md"].strip() + "\n",
            "README.md",
        )
        rd = sub1(
            rd,
            "\n## Task\n",
            "\n## Task\n"
            + render(
                texts[f"readme_{mode}.md"], {**v, "RULES": render(texts[f"readme_rules_{GROUP[fam]}.md"], v).strip()}
            ).strip()
            + "\n\n",
            "README.md",
        )
        files["README.md"][0] = rd.encode()
        tt = files["task.toml"][0].decode()
        tt = re.sub(r'^description = "RoboPaint ', 'description = "RoboPaint-strict ', tt, count=1, flags=re.M)
        sentence = render(texts[f"toml_{GROUP[fam]}.md"], v).strip().replace('"', '\\"')
        tt = re.sub(r'^(description = ".*)"$', lambda mm: mm.group(1) + " " + sentence + '"', tt, count=1, flags=re.M)
        old_fam = f"robopaint_{fam}_{slug.replace('-', '_')}"
        new_fam = f"robopaint_strict_{fam}_{slug.replace('-', '_')}"
        tt = sub1(tt, f'family = "{old_fam}"', f'family = "{new_fam}"', "task.toml")
        tt = sub1(tt, f'"{old_fam}"]', f'"{new_fam}"]', "task.toml keywords")
        tt = sub1(
            tt,
            'keywords = ["robotics", "robopaint", ',
            'keywords = ["robotics", "robopaint", "robopaint-strict", ',
            "task.toml keywords",
        )
        ev = render(cfg["oracle_evidence"][mode], v).replace('"', '\\"')
        tt = re.sub(r'^oracle_evidence = ".*"$', lambda mm: f'oracle_evidence = "{ev}"', tt, count=1, flags=re.M)
        files["task.toml"][0] = tt.encode()
        out[name] = {k: (b, m_) for k, (b, m_) in files.items()}
    return out


def normalized(planned: dict) -> dict:
    """Write both twins to a scratch tasks/ dir, run task_conventions.normalize() on each and read them back."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from task_conventions import normalize

    sys.path.pop(0)
    out = {}
    with tempfile.TemporaryDirectory(prefix="robopaint_strict_mk_") as td:
        for name, files in planned.items():
            for rel, (data, mode) in files.items():
                p = pathlib.Path(td) / name / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
                os.chmod(p, 0o755 if mode & 0o100 else 0o644)
        for name in planned:
            normalize(pathlib.Path(td) / name)
        for name in planned:
            t = pathlib.Path(td) / name
            out[name] = {
                p.relative_to(t).as_posix(): (p.read_bytes(), 0o755 if p.stat().st_mode & 0o100 else 0o644)
                for p in sorted(t.rglob("*"))
                if p.is_file() and "__pycache__" not in p.parts
            }
    return out


def sync(task: pathlib.Path, files: dict, check: bool) -> list[str]:
    """Make `task` hold exactly `files`. Returns the differences (written unless check)."""
    diffs = []
    have = (
        {p.relative_to(task).as_posix() for p in task.rglob("*") if p.is_file() or p.is_symlink()}
        if task.exists()
        else set()
    )
    have = {h for h in have if "__pycache__" not in h.split("/")}
    for rel in sorted(have - set(files)):
        diffs.append(f"remove {task.name}/{rel}")
        if not check:
            (task / rel).unlink()
    for rel, (data, mode) in sorted(files.items()):
        p = task / rel
        same = (
            p.is_file()
            and not p.is_symlink()
            and p.read_bytes() == data
            and bool(p.stat().st_mode & 0o100) == bool(mode & 0o100)
        )
        if not same:
            diffs.append(f"write  {task.name}/{rel}")
            if not check:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
                m = p.stat().st_mode & 0o777
                os.chmod(p, m | 0o111 if mode & 0o100 else m & ~0o111)
    if not check and task.exists():
        for dd in sorted((p for p in task.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
            if not any(dd.iterdir()):
                dd.rmdir()
    return diffs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "pairs", nargs="*", help="RoboPaint pairs robopaint-<family>-<target>-i00 (default: every pair of rules.json)"
    )
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    cfg = json.loads((HERE / "rules.json").read_text(encoding="utf-8"))
    todo = a.pairs or sorted(cfg["reference_path_mm"])
    bad = [b for b in todo if not SRC_RE.match(b) or b not in cfg["reference_path_mm"]]
    if bad:
        raise SystemExit(f"not a RoboPaint brush pair with a reference path in rules.json: {bad}")
    diffs = []
    for base in todo:
        for name, files in normalized(plan_pair(base, cfg)).items():
            diffs += sync(ROOT / "tasks" / name, files, a.check)
    if not a.pairs:  # strict dirs whose pair is no longer generated
        made = {f"robopaint-strict-{b[len('robopaint-') :]}-{m}" for b in todo for m in ("privileged", "standard")}
        for t in sorted((ROOT / "tasks").glob("robopaint-strict-*")):
            if t.is_dir() and t.name not in made:
                diffs.append(f"stale  {t.name} (no reference path in rules.json: remove it)")
    for d in diffs:
        print(d)
    print(
        f"{'checked' if a.check else 'generated'} RoboPaint-strict task dirs for {len(todo)} pair(s): {len(diffs)} difference(s)"
    )
    return 1 if (a.check and diffs) else 0


if __name__ == "__main__":
    sys.exit(main())
