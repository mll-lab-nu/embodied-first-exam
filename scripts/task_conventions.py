#!/usr/bin/env python3
"""Protocol v1.0 conventions for a task directory (docs/PROTOCOL.md), applied in place and idempotently.

Every generator ends with `normalize(task_dir)`, so a re-generated task equals the committed one. It also migrates a
pre-v1.0 task (old field names, protocol spelling, README layout); renaming directories is the caller's job.

    python3 scripts/task_conventions.py tasks/<task> [...]     # normalize these tasks
    python3 scripts/task_conventions.py --check tasks/<task>   # exit 1 if normalizing would change anything

What it does:
- `task.toml`: `mode` from the directory suffix (`-privileged` / `-standard`), no `tier`, `protocol = "eai-standard/2.1"`
  for standard tasks, `oracle` (+ `oracle_evidence`) for benchmarks whose oracle level is known from their files.
- protocol spelling `rcb-limited/2.x` -> `eai-standard/2.x` and "limited mode" -> "standard mode" in the task's text and
  services; the client accepts both spellings.
- `tests/test.sh` clears `/logs/verifier` first; graders write `success` (1/0) to `reward.txt` and only numbers to
  `reward.json`.
- no `results/` directory (results are published on the results site, not in the repository).
- `README.md` in the standard layout (docs/PROTOCOL.md §2.1): title, key table, Task, Difficulty, Reference solution,
  Verification, and Details for everything else.
"""
from __future__ import annotations

import re
import shutil
import sys
import tempfile
import tomllib
from pathlib import Path

CLIENT_ASSERT_OLD = 'assert str(self._spec.get("protocol", "")).startswith("rcb-limited/2."), self._spec.get("protocol")'
CLIENT_ASSERT_NEW = ('assert str(self._spec.get("protocol", "")).startswith(("eai-standard/2.", "rcb-limited/2.")), '
                     'self._spec.get("protocol")')
CLEAR_LOGS = "rm -rf /logs/verifier/*"
TEXT_SUFFIXES = {".md", ".toml", ".py", ".sh", ".yaml", ".yml", ".txt", ""}
TEXT_REPLACEMENTS = [  # (old, new), applied to task text files in order
    ("unlimited mode", "privileged mode"), ("Unlimited mode", "Privileged mode"), ("unlimited-mode", "privileged-mode"),
    ("rcb-limited/2.1", "eai-standard/2.1"), ("rcb-limited/2.0", "eai-standard/2.1"), ("rcb-limited/1.0", "eai-standard/2.1"),
    ("LIMITED MODE", "STANDARD MODE"), ("Limited-mode twin", "Standard-mode twin"), ("limited-mode twin", "standard-mode twin"),
    ("Limited-mode", "Standard-mode"), ("limited-mode", "standard-mode"), ("Limited mode", "Standard mode"),
    ("limited mode", "standard mode"), ("limited twin", "standard twin"), ("unlimited task", "privileged task"),
    ("unlimited oracle", "privileged-mode oracle"), ("unlimited expert", "privileged-mode expert"),
]
BENCHMARKS = [  # (directory prefix, label)
    ("robotwin_2_0_", "RoboTwin 2.0"), ("dextoolbench_", "DexToolBench"), ("mujoco_playground_", "MuJoCo Playground"),
    ("robosuite-", "robosuite (example task)"), ("kinder-", "KinDER"), ("humanoidbench-", "HumanoidBench"),
    ("metaworldplus-", "MetaWorld+"),
    ("robowits-", "RoboWits"), ("robopaint-strict-", "RoboPaint-strict"),  # before "robopaint-"
    ("robopaint-", "RoboPaint"), ("robolab-", "RoboLab"),
    ("behavior-", "BEHAVIOR-1K"), ("maniguard-", "ManiGuard"),
    ("molmospaces-", "MolmoSpaces"), ("myosuite-", "MyoSuite"), ("dexjoco-", "DexJoCo"),
    ("vlabench-", "VLABench"),
    ("robocasa-gr1-", "RoboCasa-GR1"),  # before "robocasa-": the first matching prefix wins
    ("robocasa-", "RoboCasa"), ("robocasa365-", "RoboCasa365"),
    ("libero-max-", "LIBERO-MAX"),
]
HEADER_KEYS = {"Benchmark", "Mode", "Twin", "Simulator / robot", "Family / instance", "Oracle", "Agent time budget",
               "Base image"}
DROP_ROWS = {"simulator / robot", "family / instance", "base image", "agent budget", "task type / tier", "tier / mode",
             "task type / mode"}
CORE = ["Task", "Difficulty", "Reference solution", "Verification"]


# ---------------------------------------------------------------------------------------------------------------------
def replace_words(s: str) -> str:
    """TEXT_REPLACEMENTS, each only where it does not continue a longer word (e.g. not inside "unlimited mode")."""
    for a, b in TEXT_REPLACEMENTS:
        s = re.sub(r"(?<![A-Za-z])" + re.escape(a), lambda _m, b=b: b, s)
    return s


def mode_of(task: Path) -> str:
    if task.name.endswith("-standard"):
        return "standard"
    if task.name.endswith("-privileged"):
        return "privileged"
    raise ValueError(f"{task.name}: task directories end in -privileged or -standard (docs/PROTOCOL.md §2.2)")


def base_of(task: Path) -> str:
    return re.sub(r"-(privileged|standard)$", "", task.name)


def bench_of(task: Path) -> str:
    return next((label for prefix, label in BENCHMARKS if task.name.startswith(prefix)), "")


def read_text(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def write_if_changed(p: Path, s: str) -> None:
    if read_text(p) != s:
        p.write_text(s, encoding="utf-8")


# ---------------------------------------------------------------------------------------------------------------------
def dtb_goals(task: Path) -> tuple[int, int] | None:
    """(goals reached, goals) by the DexToolBench oracle, from the privileged twin's README oracle row."""
    priv = task.with_name(base_of(task) + "-privileged")
    for f in (priv / "README.md", task / "README.md"):
        s = read_text(f) or ""
        m = re.search(r"\*\*(\d+)/(\d+) goals\*\*", s)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


def oracle_level(task: Path) -> tuple[str, str] | None:
    """(oracle, oracle_evidence) for benchmarks whose oracle level follows from their own files; None = keep as is."""
    n = task.name
    if n.startswith(("robotwin_2_0_", "robosuite-", "mujoco_playground_")):
        return "full", ""
    if n.startswith("dextoolbench_"):
        g = dtb_goals(task)
        if g is None:
            return None
        if g[0] >= g[1]:
            return "full", ""
        return "partial", (f"SimToolReal's pretrained policy, replayed in this scene, reaches {g[0]}/{g[1]} goals "
                           f"(solution/; README of {base_of(task)}-privileged)")
    return None


def normalize_toml(task: Path) -> None:
    p = task / "task.toml"
    s = p.read_text()
    mode = mode_of(task)
    s = re.sub(r'^name = "robot-coding-bench/[^"]*"', f'name = "robot-coding-bench/{task.name}"', s, count=1, flags=re.M)
    s = re.sub(r'(?m)^tier = .*\n', "", s)
    if re.search(r'(?m)^mode = ', s):
        s = re.sub(r'(?m)^mode = "[^"]*"', f'mode = "{mode}"', s)
    else:
        s = re.sub(r'(?m)^(family = .*\n)', rf'\1mode = "{mode}"\n', s, count=1)
    if mode == "standard":
        s = re.sub(r'(?m)^protocol = "rcb-limited/(2\.\d)"', r'protocol = "eai-standard/\1"', s)
    lvl = oracle_level(task)
    meta = tomllib.loads(s).get("metadata", {})
    if lvl and "oracle" not in meta:
        o, ev = lvl
        line = f'oracle = "{o}"\n' + (f'oracle_evidence = "{ev}"\n' if ev else "")
        s = re.sub(r'(?m)^(mode = .*\n(?:protocol = .*\n)?)', lambda m: m.group(1) + line, s, count=1)
    s = replace_words(s)
    s = s.replace('"limited-mode"', '"standard-mode"').replace('"unlimited"', '"privileged"')
    write_if_changed(p, s)


def _shared_sources() -> set[bytes]:
    """Contents of the files generators copy unchanged from scripts/eai_standard/ (the eai-standard/2.2 layer, D9): their copies
    must stay byte-identical to the source (check-tooling-identity.sh), so normalize never rewrites them."""
    src = Path(__file__).resolve().parent / "eai_standard"
    return {p.read_bytes() for p in src.glob("*") if p.is_file()} if src.is_dir() else set()


def normalize_text_files(task: Path) -> None:
    shared = _shared_sources()
    for f in sorted(task.rglob("*")):
        if not f.is_file() or f.suffix not in TEXT_SUFFIXES or f.name in ("task.toml", "README.md") or f.stat().st_size > 2_000_000:
            continue
        if f.read_bytes() in shared:
            continue
        s = read_text(f)
        if s is None:
            continue
        t = s
        t = replace_words(t)
        t = t.replace(CLIENT_ASSERT_OLD, CLIENT_ASSERT_NEW)
        if f.name == "grade.py":
            t = normalize_grader(t)
        write_if_changed(f, t)


def normalize_grader(t: str) -> str:
    """reward.txt = success (1/0); partial progress only in reward.json; no string fields in reward.json."""
    t = t.replace('open(f"{LOG}/reward.txt", "w").write(f"{reward:.4f}\\n")',
                  'open(f"{LOG}/reward.txt", "w").write(f"{int(out.get(\'success\', 0))}\\n")')
    t = t.replace("reward.txt = progress when both replays agree bit-exactly (else 0); success = every goal reached.",
                  "reward.txt = success (1/0): every goal reached and both replays agree bit-exactly; progress = goals reached / goals,\n"
                  "in reward.json.")
    t = t.replace("DexToolBench: reward = task progress (goals reached / goals); Playground: reward = success.",
                  "reward.txt = success (1/0); DexToolBench's task progress (goals reached / goals) is in reward.json.")
    old = ('    out.update(infra_error=1, grader_error=int(bool(d.get("finalize_error"))), reason=str(d.get("reason") or ""), '
           'finalize_error=str(d.get("finalize_error") or "")[:300])')
    new = ('    out.update(infra_error=1, grader_error=int(bool(d.get("finalize_error"))))   # reward.json: numbers only\n'
           '    json.dump({"reason": str(d.get("reason") or ""), "finalize_error": str(d.get("finalize_error") or "")[:300]},\n'
           '              open(f"{LOG}/infra_error.json", "w"))')
    return t.replace(old, new)


def normalize_test_sh(task: Path) -> None:
    p = task / "tests/test.sh"
    if not p.is_file():
        return
    lines = p.read_text().splitlines(keepends=True)
    cmds = [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")
            and not re.match(r"(set\s|mkdir\s+-p\s+/logs/verifier\s*$)", ln.strip())]
    if cmds and re.match(r"rm\s+-[rRf]+\s+/logs/verifier/\*", cmds[0]):
        return
    i = next((k for k, ln in enumerate(lines) if ln.strip() and not ln.lstrip().startswith("#")), len(lines))
    lines.insert(i, CLEAR_LOGS + "   # verdicts from an earlier run never survive (docs/PROTOCOL.md §2.6)\n")
    write_if_changed(p, "".join(lines))


# ---------------------------------------------------------------------------------------------------------------------
def parse_readme(s: str) -> tuple[str, list[tuple[str, str]], list[tuple[str, str]]]:
    """(intro text, table rows, sections) of a README; understands both the old layouts and the standard one."""
    lines = s.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    sections: list[tuple[str, list[str]]] = [("", [])]
    in_details = False
    for ln in lines:
        m = re.match(r"^(##|###) (.+)$", ln)
        if m and m.group(1) == "##":
            in_details = m.group(2).strip() == "Details"
            sections.append((m.group(2).strip(), []))
        elif m and in_details:
            sections.append((m.group(2).strip(), []))
        else:
            sections[-1][1].append(ln)
    rows: list[tuple[str, str]] = []
    out: list[tuple[str, str]] = []
    intro = ""
    for title, body in sections:
        text = "\n".join(body)
        body_rows, rest = [], []
        for ln in body:
            m = re.match(r"^\| ([^|]*?) \| (.*) \|$", ln)
            if m and m.group(1).strip() and set(m.group(1).strip()) != {"-"}:
                body_rows.append((m.group(1).strip(), m.group(2).strip()))
            elif ln.strip() in ("| | |", "|---|---|"):
                continue
            else:
                rest.append(ln)
        rest_text = "\n".join(rest).strip()
        if title in ("", "Task"):
            rows += body_rows
            intro = (intro + "\n\n" + rest_text).strip() if rest_text else intro
        elif title == "Details":
            rows += body_rows
            if rest_text:
                out.append(("Notes", rest_text))
        else:
            if body_rows and not rest_text:
                rows += body_rows
            else:
                out.append((title, text.strip()))
    return intro, rows, out


def image_of(task: Path) -> str:
    if task.name.endswith("-standard"):
        c = read_text(task / "environment/docker-compose.yaml") or ""
        m = re.search(r"^\s*image:\s*(\S+)", c, re.M)
        if m:
            return m.group(1)
    d = read_text(task / "environment/Dockerfile") or ""
    m = re.search(r"^FROM\s+(\S+)", d, re.M)
    return m.group(1) if m else ""


def default_difficulty(task: Path, rows: dict[str, str]) -> str:
    twin = base_of(task) + "-privileged"
    if mode_of(task) == "standard":
        return (f"Same scene, instance and success rule as `{twin}` (see its Difficulty). In standard mode the agent "
                "loses resets, privileged state and planning primitives: it sees camera images and proprioception only, "
                "acts through the client, and gets one episode, so it has to estimate the scene from images and "
                "recover from its own mistakes without starting over.")
    if task.name.startswith("dextoolbench_"):
        g = dtb_goals(task)
        ref = f" SimToolReal's pretrained policy reaches {g[0]}/{g[1]} goals here." if g else ""
        return ("Dexterous tool use: a KUKA iiwa 14 arm with a 22-DoF Sharpa HA4 hand (29 position-controlled joints) "
                "must carry the tool along DexToolBench's goal trajectory, every goal within 1.5 cm on all keypoints, "
                f"and success needs every goal.{ref}")
    if task.name.startswith("mujoco_playground_"):
        return ("MuJoCo Playground defines only a shaped RL reward; this task scores a binary success defined from it "
                f"({re.sub(r'^Playground has only a shaped RL reward(?: [(][^)]*[)])?; defined here[^:]*: ', '', rows.get('success', 'see Verification'))}), so a trajectory has to actually finish the manipulation "
                "rather than collect partial reward.")
    return "Not documented yet."


def render_readme(task: Path) -> str:
    meta = tomllib.loads((task / "task.toml").read_text())
    md, ag = meta.get("metadata", {}), meta.get("agent", {})
    old = read_text(task / "README.md") or ""
    intro, rows, sections = parse_readme(old)
    rows = [(k, v) for k, v in rows if k not in HEADER_KEYS and k.lower() not in DROP_ROWS]
    rowd = {k.lower(): v for k, v in rows}
    secd = {t: b for t, b in sections}
    mode = md.get("mode", mode_of(task))
    twin = base_of(task) + ("-privileged" if mode == "standard" else "-standard")
    seed = md.get("instance_seed")
    oracle = md.get("oracle", "")
    ev = md.get("oracle_evidence", "")
    head = [("Benchmark", bench_of(task) or "—"),
            ("Mode", f"{mode} (`{md['protocol']}`)" if mode == "standard" and md.get("protocol") else mode)]
    # a standard task always has its privileged twin (PROTOCOL §2.2), even when a generator renders it first
    head.append(("Twin", f"`{twin}`" if mode == "standard" or task.with_name(twin).is_dir() else "— (privileged only)"))
    head += [("Simulator / robot", f"`{md.get('simulator', '')}` / `{md.get('robot', '')}`"),
             ("Family / instance", f"`{md.get('family', '')}`" + (f" / seed {seed}" if seed is not None else "")),
             ("Oracle", f"`{oracle}`" + (f" — {ev}" if ev else "") if oracle else "—"),
             ("Agent time budget", f"{int(float(ag.get('timeout_sec', 0)))} s; tokens: protocol default (PROTOCOL §5)"),
             ("Base image", f"`{image_of(task)}`")]
    used = set()
    task_text = intro or meta.get("task", {}).get("description", "")
    difficulty = secd.get("Difficulty") or default_difficulty(task, rowd)
    ref = secd.get("Reference solution")
    if not ref:
        ref = rowd.get("oracle", "")
        used.add("oracle")
    ver = secd.get("Verification")
    if not ver:
        parts = [rowd[k] for k in ("verification", "grading", "metric", "success") if k in rowd]
        ver = "\n\n".join(parts)
        used.update({"verification", "grading", "metric", "success"})
    ref = ref or "See `solution/`."
    ver = ver or "See `tests/grade.py`."
    extra_rows = [(k, v) for k, v in rows if k.lower() not in used]
    extra_secs = [(t, b) for t, b in sections if t not in ("Difficulty", "Reference solution", "Verification") and b]
    out = [f"# {task.name}", "", "| | |", "|---|---|"] + [f"| {k} | {v} |" for k, v in head]
    out += ["", "## Task", task_text.strip(), "", "## Difficulty", difficulty.strip(), "",
            "## Reference solution", ref.strip(), "", "## Verification", ver.strip()]
    if extra_rows or extra_secs:
        out += ["", "## Details"]
        if extra_rows:
            out += ["| | |", "|---|---|"] + [f"| {k} | {v} |" for k, v in extra_rows]
        for t, b in extra_secs:
            out += ["", f"### {t}", b.strip()]
    s = "\n".join(out).rstrip() + "\n"
    s = re.sub(r"reward = goals / (\d+)", r"`reward.txt` = 1 iff every goal is reached (both replays agreeing); `progress` = goals / \1 in `reward.json`", s)
    s = replace_words(s)
    return re.sub(r"\n{3,}", "\n\n", s)


# ---------------------------------------------------------------------------------------------------------------------
def assert_converted(task: Path) -> None:
    """Exact-match rewrites (graders, client) must not silently miss: a surviving pre-v1.0 form is an error."""
    for f in task.rglob("grade.py"):
        if 'reward.txt", "w").write(f"{reward:.4f}' in (read_text(f) or ""):
            raise RuntimeError(f"{f}: grader still writes progress to reward.txt (update normalize_grader)")
    for f in task.rglob("rcb_client.py"):
        t = read_text(f) or ""
        if 'startswith("rcb-limited/2.")' in t and "eai-standard/2." not in t:
            raise RuntimeError(f"{f}: client accepts only rcb-limited/2.x (update CLIENT_ASSERT_OLD)")


def normalize(task: Path) -> None:
    task = Path(task)
    mode_of(task)
    if (task / "results").exists():
        shutil.rmtree(task / "results")
    normalize_toml(task)
    normalize_text_files(task)
    normalize_test_sh(task)
    write_if_changed(task / "README.md", render_readme(task))
    assert_converted(task)


def snapshot(task: Path) -> dict[str, bytes]:
    return {str(p.relative_to(task)): p.read_bytes() for p in sorted(task.rglob("*")) if p.is_file()}


def main(argv: list[str]) -> int:
    check = "--check" in argv
    dirs = [Path(a) for a in argv if a != "--check" and (Path(a) / "task.toml").is_file()]
    bad = 0
    for d in dirs:
        if check:
            with tempfile.TemporaryDirectory() as td:
                tmp = Path(td) / d.name
                shutil.copytree(d, tmp, symlinks=True)
                for sib in d.resolve().parent.glob(base_of(d) + "-*"):   # the twin, read for the README's key table
                    if sib.name != d.name:
                        (Path(td) / sib.name).symlink_to(sib)
                normalize(tmp)
                if snapshot(tmp) != snapshot(d):
                    print(f"FAIL {d}: not normalized (run scripts/task_conventions.py {d})")
                    bad = 1
        else:
            normalize(d)
    return bad


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
