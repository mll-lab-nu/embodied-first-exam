#!/usr/bin/env python3
"""Generate the RoboPaint tasks: tasks/robopaint-<family>-<target>-i<NN>-{privileged,standard} (docs/benchmarks/robopaint.md).

    python3 scripts/robopaint_strict/mk_tasks.py                          # (re)write every pair; `git diff tasks/` stays empty
    python3 scripts/robopaint_strict/mk_tasks.py --check                  # write nothing; exit 1 if a task dir differs
    python3 scripts/robopaint_strict/mk_tasks.py robopaint-kaishu-yongzibafa-i00 # these pairs only
Needs only Python 3 (no simulator, no numpy). Then `cd tasks && harbor add --scan .` when a digest changed.

Two stages, the second on the output of the first:
  1. the pair without process rules: scripts/robopaint_brush_mk_task.py --refresh into a temporary directory. It rebuilds the pair
     from its committed frozen files (instance, picture, reference plan), the committed tooling of its family's template pair
     (graders, sidecars, solution code, and the wiring of rcb_brush_strict.py) and the texts of scripts/robopaint_templates/;
  2. the process rules (this script), added to that pair:
  - every copy of the frozen instance gets the rules in target.success: max_path_mm everywhere; calligraphy and lettering
    min_mark_width_mm (colouring in = a longer path of thin marks); paintings max_scribble, max_scribble_share,
    scribble_min_mm (sweeps); calligraphy (2026-10-14) also the counted strokes (stroke_gap_mm, mark_min_width_mm,
    max_stroke_path_mm = stroke_path_factor x the reference's longest stroke, reference_longest_stroke_mm) and the sweep rule
    on those strokes. rules.json holds the family parameters and, per pair, the reference solution's path and mark width
    on the main sheet (reference_path_mm, reference_mark_width_mm, measured by measure_reference.py in the base image);
    max_path_mm = path_factor x that path rounded up to round_mm, min_mark_width_mm = mark_factor x that width rounded down to
    0.01 mm. The scene and its hash (instance_sha) do not change;
  - rcb_brush_strict.py (this directory: graders' side only, tests/, environment/scorer/, environment/sim/) applies them: the
    verifier replays with it (tests/grade.py, tests/Dockerfile), the privileged scoring service imports it (RCB_TOOL_MODULE) and the
    standard collect hook replays with it (RCB_TOOL). The tasks' wiring comes with the template pair's code; this script checks it;
  - the texts: the rules from texts/rules_<group>_<mode>.md in instruction.md (after "Target and score"), texts/readme_<mode>.md
    in README.md, a sentence in the task.toml description, the oracle evidence (rules.json: oracle_evidence, or the family's own
    entry in oracle_evidence_family, or the pair's own entry in oracle_evidence_pairs), and the pair's change log (rules.json
    change_log: README "Change Log", followed by change_log_all's entries for the mode: changes to the code every pair shares);
    texts/readme_verification_end_<mode>.md ends the README's Verification section.
The limits stay those of the reference solution they were set on (reference_path_mm, reference_mark_width_mm); a pair whose
reference solution was re-made since has its current one's path and mark width in rules.json current_reference (the evidence).
Every task ends with scripts/task_conventions.py's normalize(); a task dir holds exactly what the generator writes.

"Strict" survives only in internal names: this directory, rcb_brush_strict.py, RCB_TOOL_MODULE=rcb_brush_strict and the reward.json
key strict_ok (the process rules).
"""

from __future__ import annotations
import argparse, json, math, os, pathlib, re, subprocess, sys, tempfile

sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = ROOT / "scripts" / "robopaint_strict"
MODULE = "rcb_brush_strict.py"
GROUP = {
    "kaishu": "calligraphy",
    "xingshu": "calligraphy",
    "caoshu": "calligraphy",
    "lettering": "lettering",
    "acrylic": "painting",
    "oil": "painting",
}
SRC_RE = re.compile(r"^robopaint-(kaishu|xingshu|caoshu|lettering|acrylic|oil)-([a-z0-9]+(?:-[a-z0-9]+)*)-i\d\d$")
# the instance keys of the rules (= rcb_brush_strict.RULE_KEYS)
RULE_KEYS = ("max_path_mm", "min_mark_width_mm", "max_scribble", "max_scribble_share", "scribble_min_mm",
             "stroke_gap_mm", "mark_min_width_mm", "max_stroke_path_mm")
SPLIT_KEYS = ("stroke_gap_mm", "mark_min_width_mm", "max_stroke_path_mm")   # = rcb_brush_strict.SPLIT_KEYS
PLACES = {"privileged": ("tests/", "environment/scorer/"), "standard": ("environment/sim/",)}  # the graders' copies of MODULE
# README "Change Log" entries of every pair, by mode, written after rules.json's change_log_all: the second review of board 0067
# (kept here, next to the code they describe; rules.json holds the earlier ones).
CODE_CHANGES = {
    "privileged": [
        "2026-10-10 (review round 2, board 0067): `tests/grade.py` only. A frozen instance that the verifier's host does not "
        "rebuild (`instance_ok = 0`) is `grader_error = 1` and `infra_error = 1` (it was a plain 0 without a flag: the replays "
        "ran on another scene and say nothing about the trajectory), and every `grader_error = 1` (a replay process without a "
        "result or past its time limit) now has `infra_error = 1` next to it; every `reward.json` carries `infra_error`. The "
        "reward is 0 in these cases, as before; the pass rule, the frozen instance and the tooling are unchanged.",
        "2026-10-14 (failure analysis of 2026-10-14): the graders' `rcb_brush_strict.py`, the same file in every RoboPaint "
        "task, gained the calligraphy families' counted strokes (their own entry, where it applies); a task without those rule "
        "keys in `target.success` (lettering and the paintings) is graded exactly as before.",
    ],
    "standard": [
        "2026-10-10 (review round 2, board 0067): the service's request checks and the client. `environment/sim/server.py` "
        "checks every field of `/submit` and `/observe` before anything is executed and answers 400: a `note` that is not a "
        "string (for example a number) ended the episode with a 500 after the chunk had run, a null `dt`, `seconds` or "
        "`video_fps` ended it before anything ran, and a negative or absurd `video_fps` ended it when the video was encoded; "
        "null now means the default, `video_fps` must be in [0, 1000], and a numeric field sent as a string or a boolean is a "
        "400 too. `environment/rcb_client.py`: `Robot()` waits up to 3600 s for the service (was 600 s; no effect here, the "
        "scene builds in under a minute) and `cameras=\"name\"` (a string) is one camera, no longer its characters. The "
        "collect hook, the grader, the scene and the pass rule are unchanged; a trial that ended with reason `error` "
        "(`sim_error = 1`) right after such a request before this date was not a simulator fault.",
        "2026-10-10 (review round 3, board 0067): the shared service layer, the client and two request checks of the "
        "service (`environment/sim/rcb_limited.py`, `environment/rcb_client.py`, `environment/sim/server.py`). A camera named more than once in "
        "`cameras` is rendered and returned once (N copies of one name made the service build N x N images within "
        "the frame budget, which could exhaust its memory). A service that has given up on the episode (it could "
        "not start it, or could not resume it after its crashes) answers every request with 409 and the reason, "
        "and `Robot()` / `wait_ready()` raise `EpisodeOver` at once; before, nothing answered and they waited out "
        "their timeout (up to an hour). One call returns at most 640 images (`/spec` `max_frames_per_call`: cameras x "
        "frames, a frame with per-frame depth counts 4): a request that would exceed it is a 400 before anything runs; the "
        "control steps of an `ee_pose` chunk that is slowed down to 0.25 m/s are counted before it starts. Before, a call "
        "had no such bound: one long observation at the full frame rate, or one `ee_pose` row far outside the workspace "
        "(for example millimetres sent as metres), could hold more frames than the sidecar's memory and get the service "
        "killed, so a trial that ended `sim_crashed*` or with `resource_service_oom` right after such a request before this "
        "date was that. An `ee_pose` position too large for a finite distance is a 400 as well (it ended the episode with a "
        "500 in the middle of the chunk). The collect hook, the grader, the scene and the pass rule are unchanged.",
        "2026-10-13 (owner, boards 0085 and 0087): the sim service's clock (`environment/sim/rcb_limited.py`, "
        "`environment/sim/server.py`, the docstring of `environment/rcb_client.py`). `meta[\"time_s\"]` and "
        "`meta[\"time_left_s\"]` count from the agent's first request to the service (any endpoint), and a restarted "
        "service keeps that moment; before, they counted from the service's own start of the episode (when its scene "
        "was ready). Where the service is ready before the agent's phase begins (the harness is installed in "
        "between: 79 s in the typical recorded standard trial), that clock ran ahead of the agent's and "
        "`time_left_s` reached 0 while the agent still had that time. `/spec` says what the clock counts from "
        "(`budget.clock`), and the instruction's `## Time limit` tells the agent to plan by `time_left_s`. The "
        "service never ended an episode on this clock: the scene, the frozen instance, the pass rule and the grader "
        "are unchanged, so the task keeps its name and earlier results stand.",
        "2026-10-14 (failure analysis of 2026-10-14): the graders' `rcb_brush_strict.py`, the same file in every RoboPaint "
        "task, gained the calligraphy families' counted strokes (their own entry, where it applies); a task without those rule "
        "keys in `target.success` (lettering and the paintings) is graded exactly as before.",
    ],
}
# README "Change Log" entries of the pairs of one group (GROUP), both modes, after CODE_CHANGES.
GROUP_CHANGES = {
    "calligraphy": [
        "2026-10-14 (failure analysis of 2026-10-14, item 9): the process rules count strokes as they are written "
        "(`rcb_brush_strict.py`; the rule numbers in every copy of the instance's `target.success`: `stroke_gap_mm`, "
        "`mark_min_width_mm`, `max_stroke_path_mm`, `max_scribble`, `max_scribble_share`, `scribble_min_mm`). A contact is "
        "cut into two strokes where the brush moves more than 5 mm along the main sheet without marking it (a mark narrower "
        "than 0.1 mm), a stroke longer than `max_stroke_path_mm` (5 x the reference solution's longest stroke) counts as "
        "several, and the paintings' sweep rule (at most 10 % of the path in strokes longer than 12 x their bounding box's "
        "diagonal) applies to these strokes. Before, the cap counted contacts: pieces written separately and joined by a "
        "press too light to ink counted as one stroke, and so did a contact held down to write over and over. The scene "
        "(`instance_sha`), the picture rule and the reference solution are unchanged, and the reference passes with each of "
        "its strokes counted once. Results graded before this change are re-graded from their recorded trajectories, "
        "nothing is re-run (scripts/robopaint_strict/regrade.py). The instruction states the rule.",
    ],
}
WIRING = {  # (file, what it holds when rcb_brush_strict.py is wired in), from the template pair's code
    "privileged": (
        ("tests/grade.py", MODULE),
        ("tests/Dockerfile", f" {MODULE} "),
        ("environment/docker-compose.yaml", "RCB_TOOL_MODULE: rcb_brush_strict"),
    ),
    "standard": (("environment/docker-compose.yaml", f"RCB_TOOL: /srv/{MODULE}"),),
}


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
    """(the rule keys added to target.success, the text values) of the pair <base>."""
    fam = SRC_RE.match(base).group(1)
    F = cfg["families"][fam]
    ref = float(cfg["reference_path_mm"][base])
    cur = cfg.get("current_reference", {}).get(base, {})  # a reference solution re-made after the limits were set
    ev_path = float(cur.get("path_mm", ref))
    step = float(F["round_mm"])
    budget = math.ceil(F["path_factor"] * ref / step - 1e-9) * step
    rule = {"max_path_mm": float(budget)}
    v_mark = {}
    if "mark_factor" in F:  # calligraphy, lettering: colouring in = a long path AND thin marks
        ref_w = float(cfg["reference_mark_width_mm"][base])
        ev_w = float(cur.get("mark_width_mm", ref_w))
        min_w = math.floor(F["mark_factor"] * ref_w / 0.01 + 1e-9) * 0.01
        rule["min_mark_width_mm"] = round(min_w, 2)
        v_mark = {
            "MIN_MARK_WIDTH_MM": f"{min_w:.2f}",
            "REF_MARK_WIDTH_MM": f"{ref_w:.2f}",
            "MARK_FACTOR": fmt(F["mark_factor"]),
            "EVIDENCE": f"path_mm {ev_path:.0f} and mark_width_mm {ev_w:.2f}, against the colouring-in limits {fmt(budget)} mm and "
            f"{min_w:.2f} mm",
        }
    v_count = {}
    if "stroke_gap_mm" in F:  # calligraphy (2026-10-14): the cap counts strokes (marked pieces), not contacts
        longest = float(cfg["reference_longest_stroke_mm"][base])
        sstep = float(F["stroke_round_mm"])
        lim = math.ceil(F["stroke_path_factor"] * longest / sstep - 1e-9) * sstep
        rule.update({"stroke_gap_mm": float(F["stroke_gap_mm"]), "mark_min_width_mm": float(F["mark_min_width_mm"]),
                     "max_stroke_path_mm": float(lim)})
        v_count = {"STROKE_GAP_MM": fmt(F["stroke_gap_mm"]), "MARK_MIN_WIDTH_MM": fmt(F["mark_min_width_mm"]),
                   "MAX_STROKE_PATH_MM": fmt(lim), "REF_LONGEST_STROKE_MM": f"{longest:.0f}",
                   "STROKE_PATH_FACTOR": fmt(F["stroke_path_factor"])}
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
        "EVIDENCE": f"path_mm {ev_path:.0f} of the {fmt(budget)} mm budget; its strokes are sweeps",
        **v_mark,
        **v_count,
    }
    return rule, v


def add_rule(raw: bytes, rule: dict) -> bytes:
    """An instance.json (indent=1, ensure_ascii=False, no trailing newline, as rcb_brush_score writes it) with exactly the rules of
    `rule` at the end of target.success (a committed instance already holds them; they are replaced, never doubled)."""
    d = json.loads(raw.decode("utf-8"))
    if json.dumps(d, indent=1, ensure_ascii=False).encode("utf-8") != raw:
        raise SystemExit("an instance.json is not in rcb_brush_score's format (indent=1, ensure_ascii=False)")
    for k in RULE_KEYS:
        d["target"]["success"].pop(k, None)
    d["target"]["success"].update(rule)
    return json.dumps(d, indent=1, ensure_ascii=False).encode("utf-8")


def sub1(s: str, old: str, new: str, where: str) -> str:
    if s.count(old) != 1:
        raise SystemExit(f"{where}: expected exactly one {old!r} ({s.count(old)} found)")
    return s.replace(old, new)


def sub_re1(s: str, pattern: str, repl, where: str) -> str:
    s2, n = re.subn(pattern, repl, s, count=1, flags=re.M)
    if n != 1:
        raise SystemExit(f"{where}: no match for {pattern!r}")
    return s2


def rebuild_base(todo: list[str], out: pathlib.Path) -> None:
    """Stage 1: the pairs <todo> without process rules, written to `out` by robopaint_brush_mk_task.py --refresh from the committed
    pairs under tasks/ (their frozen files; the template pair of each family under tasks/ for the tooling)."""
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "robopaint_brush_mk_task.py"),
        "--refresh",
        *[str(ROOT / "tasks" / f"{b}-privileged") for b in todo],
        "--template-root",
        str(ROOT / "tasks"),
        "--out-root",
        str(out),
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        raise SystemExit(f"robopaint_brush_mk_task.py --refresh failed ({p.returncode}):\n{(p.stdout + p.stderr)[-3000:]}")


def plan_pair(base: str, cfg: dict, stage: pathlib.Path) -> dict:
    """{task dir name: {rel path: (bytes, mode)}} for both twins of the pair <base>, from stage 1's output in `stage`."""
    fam, slug = SRC_RE.match(base).groups()
    rule, v = rules_for(base, cfg)
    module = (HERE / MODULE).read_bytes()
    texts = {p.name: p.read_text(encoding="utf-8") for p in (HERE / "texts").glob("*.md")}
    out = {}
    for mode in ("privileged", "standard"):
        name = f"{base}-{mode}"
        src = stage / name
        if not (src / "task.toml").is_file():
            raise SystemExit(f"{src}: missing (stage 1 did not write it)")
        files = {
            p.relative_to(src).as_posix(): [p.read_bytes(), 0o755 if p.stat().st_mode & 0o100 else 0o644]
            for p in sorted(src.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts
        }
        for rel in list(files):
            if rel.endswith("instance.json"):
                # the agent's own copy (privileged environment/instance.json) needs no counted-stroke numbers: its
                # s.score() asks the scoring service, and the instruction states them (check-robopaint-leak.sh admits the
                # earlier rule keys there only)
                agent = mode == "privileged" and rel == "environment/instance.json"
                files[rel][0] = add_rule(files[rel][0], {k: x for k, x in rule.items() if not (agent and k in SPLIT_KEYS)})
        for place in PLACES[mode]:
            files[place + MODULE] = [module, 0o644]
        for rel, needle in WIRING[mode]:
            if needle not in files[rel][0].decode():
                raise SystemExit(
                    f"{name}/{rel}: {MODULE} is not wired in ({needle!r} missing); the wiring is part of the template pair's code"
                )
        # texts
        ins = files["instruction.md"][0].decode()
        block = render(texts[f"rules_{GROUP[fam]}_{mode}.md"], v).rstrip() + "\n\n"
        m = re.search(r"^## Target and score\n.*?(?=^## )", ins, re.S | re.M)
        if not m:
            raise SystemExit(f"{src}/instruction.md: no '## Target and score' section")
        files["instruction.md"][0] = (ins[: m.end()] + block + ins[m.end() :]).encode()
        rd = files["README.md"][0].decode()
        if mode == "privileged":
            rd = sub1(
                rd,
                "Oracle label `partial`: the recorded oracle runs predate this version's files (task.toml `oracle_evidence`); human "
                "review in PR #3.",
                "Oracle label `partial`: the reference solution, scored under the process rules (task.toml `oracle_evidence`).",
                "README.md",
            )
        else:
            rd = sub1(
                rd,
                "label `partial` (task.toml `oracle_evidence`: the recorded runs predate this version), human review in PR #3.",
                "label `partial` (task.toml `oracle_evidence`: the reference solution, scored under the process rules).",
                "README.md",
            )
        rd = sub1(
            rd,
            "\n## Verification\n",
            "\n## Verification\n" + texts[f"readme_verification_{mode}.md"].strip() + "\n",
            "README.md",
        )
        # the verifier's own conditions (no verdict, a file that is not a trajectory, its time), at the end of the section
        rd = sub_re1(
            rd,
            r"(?s)(\n## Verification\n.*?)(?=\n## )",
            lambda mm: mm.group(1).rstrip("\n") + "\n" + texts[f"readme_verification_end_{mode}.md"].strip() + "\n",
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
        # the pair's own entries (change_log), then the entries of every pair of this mode (change_log_all)
        log = (list(cfg.get("change_log", {}).get(base) or []) + list(cfg.get("change_log_all", {}).get(mode) or [])
               + CODE_CHANGES[mode] + GROUP_CHANGES.get(GROUP[fam], []))
        if log:  # normalize() files it under Details as "### Change Log"
            entries = "\n".join(f"- {e}" for e in log) + "\n"
            if "\n### Change Log\n" in rd:  # the family's template has the section (oil): its entries first
                rd = sub_re1(
                    rd,
                    r"(?s)(\n### Change Log\n.*?)(?=\n#{2,3} |\Z)",
                    lambda mm: mm.group(1).rstrip("\n") + "\n" + entries,
                    "README.md",
                )
            else:
                rd = rd.rstrip("\n") + "\n\n## Change Log\n" + entries
        files["README.md"][0] = rd.encode()
        tt = files["task.toml"][0].decode()
        sentence = render(texts[f"toml_{GROUP[fam]}.md"], v).strip().replace('"', '\\"')
        tt = sub_re1(tt, r'^(description = ".*)"$', lambda mm: mm.group(1) + " " + sentence + '"', "task.toml")
        evs = (
            cfg.get("oracle_evidence_pairs", {}).get(base)
            or cfg.get("oracle_evidence_family", {}).get(fam)
            or cfg["oracle_evidence"]
        )
        ev = render(evs[mode], v).replace('"', '\\"')
        tt = sub_re1(tt, r'^oracle_evidence = ".*"$', lambda mm: f'oracle_evidence = "{ev}"', "task.toml")
        files["task.toml"][0] = tt.encode()
        out[name] = {k: (b, m_) for k, (b, m_) in files.items()}
    return out


def normalized(planned: dict) -> dict:
    """Write both twins to a scratch tasks/ dir, run task_conventions.normalize() on each and read them back."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from task_conventions import normalize

    sys.path.pop(0)
    out = {}
    with tempfile.TemporaryDirectory(prefix="robopaint_mk_") as td:
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
    ap.add_argument("pairs", nargs="*", help="pairs robopaint-<family>-<target>-i<NN> (default: every pair of rules.json)")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    cfg = json.loads((HERE / "rules.json").read_text(encoding="utf-8"))
    todo = a.pairs or sorted(cfg["reference_path_mm"])
    bad = [b for b in todo if not SRC_RE.match(b) or b not in cfg["reference_path_mm"]]
    if bad:
        raise SystemExit(f"not a RoboPaint brush pair with a reference path in rules.json: {bad}")
    diffs = []
    with tempfile.TemporaryDirectory(prefix="robopaint_base_") as td:
        stage = pathlib.Path(td)
        rebuild_base(todo, stage)
        for base in todo:
            for name, files in normalized(plan_pair(base, cfg, stage)).items():
                diffs += sync(ROOT / "tasks" / name, files, a.check)
    if not a.pairs:  # task dirs whose pair is no longer generated
        made = {f"{b}-{m}" for b in todo for m in ("privileged", "standard")}
        for t in sorted((ROOT / "tasks").glob("robopaint-*")):
            if t.is_dir() and t.name not in made:
                diffs.append(f"stale  {t.name} (no reference path in rules.json: remove it)")
    for d in diffs:
        print(d)
    print(f"{'checked' if a.check else 'generated'} RoboPaint task dirs for {len(todo)} pair(s): {len(diffs)} difference(s)")
    return 1 if (a.check and diffs) else 0


if __name__ == "__main__":
    sys.exit(main())
