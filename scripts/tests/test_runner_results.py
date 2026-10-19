#!/usr/bin/env python3
"""Runner-side tools of board 0105 (F-M2), standard library and bash only:

- scripts/write_task_results.py publishes a trial the verifier never graded (no reward.json), one Harbor ended with an
  exception other than the agent's cutoff (AgentTimeoutError), or one stopped by a model-account failure as "not a
  result", never as the agent's 0; a verdict, the cutoff and the token budget stay results;
- scripts/clamp_cpus.py clamps every CPU cap of a task copy to the host's count (PROTOCOL §2.10) and nothing else, and
  refuses the repository's own tasks;
- scripts/run_agent_batch.sh runs every job from its own copy of the task, every file stamped with its content's mtime
  (scripts/stamp_mtimes.py, issue #258), with a CPU cap above HOST_CPUS clamped in that copy (a stand-in `harbor` on
  PATH records what it was given), removes the copy afterwards, and leaves tasks/ unchanged;
- (board 0121 M4) a trial whose last model calls failed at the usage gateway, or whose job the gateway died in, is not a
  result; with GATEWAY=1 the runner restarts a dead gateway before the next job."""
import functools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLAMP = [sys.executable, str(ROOT / "scripts/clamp_cpus.py")]
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as tc  # noqa: E402  (task_dir / iter_tasks: the task tree)
TASK = "robotwin_2_0_stack_blocks_two-standard"          # any task of the repository (write_task_results looks it up)
BIG = "behavior-boxing-food-after-dinner-i00"             # its standard twin's sidecar caps are 12 CPUs
HB = "humanoidbench-loco-walk-i00-privileged"            # [environment] cpus = 16
SMALL = "robotwin_2_0_stack_blocks_two"                  # caps of at most 8
fails = []


def check(cond, what):
    if not cond:
        fails.append(what)
        print("FAIL", what)


def result_line(td: Path, result: dict, reward=None, gateway=None, codex=None, down=False) -> str:
    jobs = td / "jobs"; job = f"j{len(list(jobs.glob('*'))) if jobs.exists() else 0}"
    trial = jobs / job / f"{TASK}__abc"
    trial.mkdir(parents=True)
    if down:                                   # run_agent_batch.sh found the usage gateway dead after the job
        (jobs / job / "gateway_down.json").write_text("{}")
    (trial / "result.json").write_text(json.dumps({"task_name": TASK, **result}))
    if reward is not None:
        (trial / "verifier").mkdir()
        (trial / "verifier/reward.json").write_text(reward if isinstance(reward, str) else json.dumps(reward))
    if gateway is not None:
        (trial / "gateway").mkdir()
        (trial / "gateway/totals.json").write_text(json.dumps(gateway))
    if codex is not None:
        (trial / "agent").mkdir()
        (trial / "agent/codex.txt").write_text(codex)
    out = td / "out" / job
    r = subprocess.run([sys.executable, str(ROOT / "scripts/write_task_results.py"), str(jobs), job, "codex-x-high", "label",
                        "--out", str(out)], capture_output=True, text=True)
    check(r.returncode == 0, f"write_task_results.py exited {r.returncode}: {r.stderr[-500:]}")
    readme = (out / TASK / "codex-x-high" / "README.md").read_text()
    return next(l for l in readme.splitlines() if l.startswith("| result |"))


def test_results():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        timeout = {"exception_info": {"exception_type": "AgentTimeoutError"}}
        cases = [
            ("a success", {}, {"success": 1}, None, None, "**1 (success)**"),
            ("the agent's 0", {}, {"success": 0}, None, None, "**0**"),
            ("0 at the cutoff", timeout, {"success": 0}, None, None, "**0**"),
            ("a success at the cutoff", timeout, {"success": 1}, None, None, "**1 (success)**"),
            ("over the token budget", {}, {"success": 1}, {"over_token_budget": True}, None, "over the token budget"),
            ("infra_error", {}, {"success": 0, "infra_error": 1}, None, None, "not a result"),
            ("grader_error", timeout, {"success": 0, "grader_error": 1}, None, None, "not a result"),
            ("compose up failed, no reward.json",
             {"exception_info": {"exception_type": "RuntimeError", "exception_message": "docker compose up failed: range of CPUs is from 0.01 to 8.00"}},
             None, None, None, "not a result"),
            ("no reward.json, no exception", {}, None, None, None, "not a result"),
            ("no reward.json at the cutoff", timeout, None, None, None, "not a result"),
            ("a corrupt reward.json", {}, '{"success": 0, "inf', None, None, "not a result"),
            ("the verifier timed out after a reward", {"exception_info": {"exception_type": "VerifierTimeoutError"}}, {"success": 0}, None, None, "not a result"),
            ("the harness died", {"exception_info": {"exception_type": "NonZeroAgentExitCodeError"}}, {"success": 0}, None, None, "not a result"),
            ("a model-account failure", {}, {"success": 0}, None,
             '{"type": "turn.failed", "error": {"message": "unexpected status 429 Too Many Requests: usage limit reached"}}\n', "not a result"),
            ("a success the account check would flag", {}, {"success": 1}, None,
             '{"type": "turn.failed", "error": {"message": "unexpected status 429 Too Many Requests"}}\n', "**1 (success)**"),
            ("over the budget without a reward", {}, None, {"over_token_budget": True}, None, "over the token budget"),
            ("over the budget, infra_error", {}, {"success": 0, "infra_error": 1}, {"over_token_budget": True}, None, "not a result"),
        ]
        # board 0121 M4: the model API unreachable through the usage gateway at the end of the trial: not the agent's 0
        gw = lambda n, last="unreachable: ConnectionRefusedError": {"requests": 3, "input": 10, "output": 2, "upstream_failures": n + 1,
                                                                    "failures_in_a_row": n, "last_upstream_failure": last}
        cases += [
            ("the gateway's upstream unreachable at the end", {}, {"success": 0}, gw(6), None, "not a result"),
            ("a stream broken off at the end, at the cutoff", timeout, {"success": 0}, gw(1, "stream broken off: TimeoutError"), None,
             "not a result"),
            ("gateway failures the agent got past", {}, {"success": 0}, gw(0), None, "**0**"),
            ("a success after gateway failures", {}, {"success": 1}, gw(2), None, "**1 (success)**"),
            ("over the budget with gateway failures", {}, {"success": 0}, {**gw(4), "over_token_budget": 1}, None, "over the token budget"),
        ]
        for name, result, reward, gateway, codex, want in cases:
            line = result_line(td, result, reward, gateway, codex)
            check(want in line, f"write_task_results: {name}: {line}")
            if want != "not a result":
                check("not a result" not in line, f"write_task_results: {name} is a result: {line}")
        line = result_line(td, {}, {"success": 0}, down=True)
        check("not a result" in line and "gateway was down" in line, f"write_task_results: the gateway down after the job: {line}")
        line = result_line(td, {"exception_info": {"exception_type": "EnvironmentStartTimeoutError"}})
        check("EnvironmentStartTimeoutError" in line and "no reward.json" in line, f"the reason names Harbor's exception: {line}")


UNVALIDATED = "humanoidbench-loco-walk-i00-standard-realtime"   # oracle = "none": ranked with validated tasks, marked
VALIDATED_RT = "humanoidbench-loco-sit-simple-i00-standard-realtime"   # oracle = "full", the same configuration as UNVALIDATED
WTR = [sys.executable, str(ROOT / "scripts/write_task_results.py")]


def make_trial(jobs: Path, job: str, name: str, task: str, started: str, reward=None, result=None, config=None) -> Path:
    t = jobs / job / f"{task}__{name}"
    t.mkdir(parents=True)
    (t / "result.json").write_text(json.dumps({"task_name": task, "id": name, "started_at": started, **(result or {})}))
    if reward is not None:
        (t / "verifier").mkdir()
        (t / "verifier/reward.json").write_text(json.dumps(reward))
    if config is not None:
        (t / "config.json").write_text(json.dumps(config))
    return t


def write(jobs: Path, job: str, out: Path) -> subprocess.CompletedProcess:
    r = subprocess.run(WTR + [str(jobs), job, "codex-x-high", "label", "--out", str(out)], capture_output=True, text=True)
    check(r.returncode == 0, f"write_task_results.py exited {r.returncode}: {r.stderr[-500:]}")
    return r


def test_config_and_attempts():
    """PROTOCOL v2.0 / docs/protocol/running.md: every result records its effective configuration (config.json); an infrastructure
    failure (not a result) is voided and never counted, one retry replaces it, a voided attempt never replaces a counted
    one, more than 2 attempts of one task x run id are flagged; a trial of another task version is legacy."""
    infra = {"success": 0, "infra_error": 1}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td); jobs, out = td / "jobs", td / "out"
        dg = (tc.task_dir(TASK) / "DIGEST").read_text().strip().removeprefix("sha256:")
        make_trial(jobs, "a", "t1", TASK, "2026-10-14T01:00:00Z", infra, {"task_checksum": dg})
        make_trial(jobs, "a", "t2", TASK, "2026-10-14T02:00:00Z", {"success": 1}, {"task_checksum": dg})
        write(jobs, "a", out)
        res = out / TASK / "codex-x-high"
        cfg = json.loads((res / "config.json").read_text())
        for k, v in {"protocol_version": "2.0", "mode": "standard", "network": "allowlist", "validated": True, "result": "success",
                     "counted": True, "attempts": 2, "attempts_over_cap": False, "seed_source": "default", "digest_match": True,
                     "trial": f"{TASK}__t2"}.items():
            check(cfg.get(k) == v, f"config.json {k} = {cfg.get(k)!r}, want {v!r}")
        for k in ("cutoff_s", "reset_budget", "slowdown", "seed", "digest"):
            check(k in cfg, f"config.json has no {k}")
        att = json.loads((res / "attempts.json").read_text())["attempts"]
        check([a["counted"] for a in att] == [False, True], f"attempts.json: the infra attempt is counted: {att}")
        check("| configuration | protocol 2.0, standard" in (res / "README.md").read_text(), "README has no configuration row")
        # a later infrastructure failure of the same task x run id never replaces the counted result, and a third attempt is flagged
        make_trial(jobs, "b", "t3", TASK, "2026-10-14T03:00:00Z", infra, {"task_checksum": dg})
        r = write(jobs, "b", out)
        cfg = json.loads((res / "config.json").read_text())
        check(cfg.get("trial") == f"{TASK}__t2" and cfg.get("result") == "success", f"a voided attempt replaced the result: {cfg}")
        check("WARN" in r.stdout and "3 attempts" in r.stdout, f"no WARN for 3 attempts: {r.stdout}")
        check(len(json.loads((res / "attempts.json").read_text())["attempts"]) == 3, "attempts.json does not list the third attempt")
        # only infrastructure failures: the folder shows the latest as not a result, not counted
        make_trial(jobs, "c", "u1", f"{SMALL}-privileged", "2026-10-14T01:00:00Z", infra)
        write(jobs, "c", out)
        cfg = json.loads((out / f"{SMALL}-privileged" / "codex-x-high" / "config.json").read_text())
        check(cfg.get("result") == "not_a_result" and cfg.get("counted") is False and cfg.get("not_a_result_reason"),
              f"an infrastructure failure is counted: {cfg}")
        # a trial of another version of the task (its checksum is not today's DIGEST): legacy fields, still written
        make_trial(jobs, "d", "l1", f"{SMALL}-standard", "2026-10-14T01:00:00Z", {"success": 0}, {"task_checksum": "0" * 64})
        write(jobs, "d", out)
        cfg = json.loads((out / f"{SMALL}-standard" / "codex-x-high" / "config.json").read_text())
        check(cfg.get("cutoff_s") == "legacy" and cfg.get("digest_match") is False and cfg.get("mode") == "standard"
              and cfg.get("result") == "fail", f"legacy trial: {cfg}")
        # a legacy result.json without a checksum: derived from task.toml as it is
        make_trial(jobs, "e", "l2", UNVALIDATED, "2026-10-14T01:00:00Z", {"success": 0})
        write(jobs, "e", out)
        cfg = json.loads((out / UNVALIDATED / "codex-x-high" / "config.json").read_text())
        check(cfg.get("validated") is False and cfg.get("slowdown") is not None and cfg.get("digest_match") is None,
              f"an unvalidated realtime task without a checksum: {cfg}")
        # the seed the runner chose: its copy of the task says it (scripts/task_seed.py materialize)
        copy = td / "copy" / TASK
        shutil.copytree(tc.task_dir(TASK), copy)
        s = (copy / "task.toml").read_text()
        (copy / "task.toml").write_text(re.sub(r"(?m)^(\[metadata\.seeds\]\n(?:.*\n)*?default = )\d+", r"\g<1>4242", s, count=1))
        make_trial(jobs, "f", "s1", TASK, "2026-10-14T01:00:00Z", {"success": 0}, None, {"task": {"path": str(copy)}})
        write(jobs, "f", td / "out2")
        cfg = json.loads((td / "out2" / TASK / "codex-x-high" / "config.json").read_text())
        check(cfg.get("seed") == 4242 and cfg.get("seed_source") == "runner copy", f"the runner's seed: {cfg}")


def summary_code() -> str:
    s = (ROOT / "scripts/run_agent_batch.sh").read_text()
    m = re.search(r"(?ms)^summary\(\) \{.*?<<'PY'\n(.*?)^PY$", s)
    check(m is not None, "run_agent_batch.sh has no summary() heredoc")
    return m.group(1) if m else ""


def test_summary_grouping():
    """run_agent_batch.sh's summary: one table per comparable configuration, unvalidated tasks ranked in it (marked),
    voided trials not counted in a success rate."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td); jobs = td / "jobs"
        make_trial(jobs, "bx-standard-a", "t1", TASK, "2026-10-14T01:00:00Z", {"success": 0, "infra_error": 1})
        make_trial(jobs, "bx-standard-a", "t2", TASK, "2026-10-14T02:00:00Z", {"success": 1})
        make_trial(jobs, "bx-privileged-a", "p1", f"{SMALL}-privileged", "2026-10-14T01:00:00Z", {"success": 0})
        make_trial(jobs, "bx-standard-realtime-b", "r1", UNVALIDATED, "2026-10-14T01:00:00Z", {"success": 1})
        make_trial(jobs, "bx-standard-realtime-b", "r2", VALIDATED_RT, "2026-10-14T01:00:00Z", {"success": 0})
        # a core set naming the fixed tasks here (the real list changes over time); test_core_set covers the marking
        sys.path.insert(0, str(ROOT / "scripts"))
        import task_conventions as tc
        (td / "core_set.toml").write_text("".join(
            f'[[task]]\ntask = "{tc.base_of(Path(t))}"\ndefault_mode = "{tc.mode_of(Path(t))}"\n' for t in
            (TASK, f"{SMALL}-privileged", UNVALIDATED, VALIDATED_RT)))
        r = subprocess.run([sys.executable, "-", str(jobs), "bx", str(ROOT)], input=summary_code(), capture_output=True, text=True,
                           env={**os.environ, "RCB_CORE_SET_FILE": str(td / "core_set.toml")})
        check(r.returncode == 0, f"summary failed: {r.stderr[-800:]}")
        out = r.stdout
        check("## Unvalidated" not in out and out.count("\n## protocol 2.0, ") == 3, f"not one table per configuration:\n{out}")
        rt = out[out.index("standard-realtime, "):]
        check(f"| {UNVALIDATED} (unvalidated) |" in rt and f"| {VALIDATED_RT} |" in rt,
              f"the unvalidated task is not ranked (marked) with the validated one of its configuration:\n{out}")
        check("Success (results only): 1 / 2 (validated tasks: 0 / 1); 0 voided." in rt, f"the shared table's rate:\n{out}")
        check("Success (results only): 1 / 1; 1 voided." in out, f"a voided trial counted in the success rate:\n{out}")
        check("not a result (voided" in out, f"the voided trial is not marked:\n{out}")


def test_core_set():
    """PROTOCOL §4: the core set (docs/core_set.toml: task + default_mode) is valid, marks every mode dir of its listed
    tasks `core` and every other dir `excluded` (recorded with the result as `set`, never part of config_key), and the
    batch summary marks the trials outside it and leaves them out of the rate."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import task_conventions as tc
    check(not tc.check_core_set(), f"docs/core_set.toml: {tc.check_core_set()[:3]}")   # this test is in run_invariants.sh
    names = [p.name for p in tc.iter_tasks()]
    cs = tc.core_set()
    def entry(t, **k):                                   # a valid entry for task t, with the fields in k changed
        f = {"task": t, "default_mode": cs.get(t, "standard"), **k}
        return "[[task]]\n" + "".join(f'{n} = "{v}"\n' for n, v in f.items())
    ANY, ANY2 = sorted(cs)[:2]
    with tempfile.TemporaryDirectory() as td:
        bad = Path(td) / "core_set.toml"
        bad.write_text(entry("behavior-no-such-task-i00") + entry(ANY, default_mode="x") + entry(ANY2, luna="failed")
                       + entry("../tasks/" + ANY) + entry(f"{ANY}-{cs[ANY]}"))
        found = tc.check_core_set(path=bad)
        check(len(found) == 5, f"check_core_set: want a missing dir, a wrong mode, an unknown field, a path and a dir name, got {found}")
        (Path(td) / "twice.toml").write_text(entry(ANY) + entry(ANY))
        check(any("twice" in x for x in tc.check_core_set(path=Path(td) / "twice.toml")), "a task listed twice is not found")
        check(tc.check_core_set(path=Path(td) / "none.toml") != [], "a missing list passes")
        (Path(td) / "toplevel.toml").write_text('generated_from = "x"\n' + entry(ANY))
        check(any("top-level" in x for x in tc.check_core_set(path=Path(td) / "toplevel.toml")), "an unknown top-level key passes")
    core = set(tc.core_tasks())
    check(len(core) == len(cs) and all(tc.mode_of(Path(d)) == cs[tc.base_of(Path(d))] for d in core),
          "core_tasks(): not one default-mode dir per core task")
    # a listed standard dir and an unlisted one in the same configuration (one summary table); the list changes over
    # time, so both are looked up
    key = functools.lru_cache(maxsize=None)(lambda t: tc.config_key(tc.effective_config(tc.task_dir(t))))
    IN = OUT = None
    for c in (t for t in names if t.endswith("-standard") and tc.base_of(Path(t)) in cs):
        same = sorted((t for t in names if t.endswith("-standard") and tc.base_of(Path(t)) not in cs),
                      key=lambda t: t.split("-")[0] != c.split("-")[0])[:200]
        OUT = next((t for t in same if key(t) == key(c)), None)
        if OUT:
            IN = c
            break
    if IN is None:
        print("note: no core standard dir with an excluded one of the same configuration; the core-set test is skipped")
        return
    check(tc.set_of(tc.task_dir(IN)) == "core" and tc.set_of(tc.task_dir(OUT)) == "excluded",
          f"set_of: {IN} {tc.set_of(tc.task_dir(IN))}, {OUT} {tc.set_of(tc.task_dir(OUT))}")
    a, b = tc.effective_config(tc.task_dir(IN)), tc.effective_config(tc.task_dir(OUT))
    check(a.get("set") == "core" and b.get("set") == "excluded", f"effective_config set: {a.get('set')}, {b.get('set')}")
    check(tc.config_key(a) == tc.config_key(dict(a, set="excluded")), "the set is part of config_key")
    with tempfile.TemporaryDirectory() as td:
        jobs = Path(td) / "jobs"
        make_trial(jobs, "bx-standard-a", "e1", OUT, "2026-10-14T01:00:00Z", {"success": 1})
        make_trial(jobs, "bx-standard-a", "c1", IN, "2026-10-14T02:00:00Z", {"success": 0})
        r = subprocess.run([sys.executable, "-", str(jobs), "bx", str(ROOT)], input=summary_code(), capture_output=True, text=True)
        check(r.returncode == 0, f"summary failed: {r.stderr[-800:]}")
        check(re.search(rf"\| {OUT}( \(unvalidated\))? \(not core\) \|", r.stdout) is not None,
              f"the trial outside the core set is not marked:\n{r.stdout}")
        check(re.search(r"Success \(results only\): 0 / 1( \([^)]*\))?; 0 voided; 1 result\(s\) of tasks outside the core set not counted\.",
                        r.stdout) is not None,
              f"the trial outside the core set counted in the rate:\n{r.stdout}")


def test_benchmarks():
    """Every task dir has its benchmark label, the label results and reports are grouped by (dataset_manifest.py,
    the pool): the first BENCHMARKS prefix the name starts with. The real tree is clean; a name no prefix claims is
    found."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import task_conventions as tc
    bad = tc.check_benchmarks()
    check(not bad, f"benchmark labels: {bad[:5]}")
    check(tc.bench_of(Path("roboolympics-fun-sprint-i00")) == "RoboOlympics-Fun"
          and tc.bench_of(Path("roboolympics-match-tabletennis-match-i01-standard-realtime")) == "RoboOlympics-Match"
          and tc.bench_of(Path("roboolympics-sprint-i00-standard")) == ""
          and tc.bench_of(Path("robocasa-gr1-x-i00-standard")) == "RoboCasa-GR1", "bench_of: the first matching prefix")
    with tempfile.TemporaryDirectory() as td:
        for n in ("roboolympics-fun-sprint-i00-privileged", "no-such-bench-i00-standard"):
            (Path(td) / "roboolympics-fun" / n).mkdir(parents=True)
            (Path(td) / "roboolympics-fun" / n / "task.toml").write_text("")
        found = tc.check_benchmarks(Path(td))
        check(not any("sprint" in x for x in found) and any("no-such-bench" in x and "no benchmark label" in x for x in found),
              f"an unclaimed name: {found[:3]}")
    with tempfile.TemporaryDirectory() as td:            # the layout: tasks/<benchmark folder>/<task>/ and nothing else
        td = Path(td)
        for rel in ("robolab/robolab-x-i00-privileged", "robowits/robolab-y-i00-standard", "kinder-z-i00-privileged",
                    "robolab/robolab-w-i00-standard/deeper"):
            (td / rel).mkdir(parents=True)
        for rel in ("robolab/robolab-x-i00-privileged", "robowits/robolab-y-i00-standard", "kinder-z-i00-privileged",
                    "robolab/robolab-w-i00-standard/deeper"):
            (td / rel / "task.toml").write_text("")
        (td / "README.md").write_text("")
        found = tc.check_layout(td)
        check(not any("robolab-x" in x for x in found), f"a task dir in its folder was flagged: {found}")
        check(any("robolab-y" in x and "belongs in tasks/robolab/" in x for x in found), f"a task in another benchmark's folder: {found}")
        check(any("kinder-z" in x and "not a benchmark folder" in x for x in found), f"a flat task dir: {found}")
        check(any("robolab-w-i00-standard" in x and "not a task dir" in x for x in found), f"a task dir nested deeper: {found}")
        check(not any("README" in x for x in found), f"tasks/README.md was flagged: {found}")
        check(not any("no folder" in x or "not a BENCHMARKS label" in x for x in found), f"BENCHMARK_DIRS: {found}")
    check(tc.task_dir(TASK) == ROOT / "tasks" / "robotwin-2" / TASK and tc.task_relpath(TASK) == f"tasks/robotwin-2/{TASK}"
          and (tc.task_dir(TASK) / "task.toml").is_file(), f"task_dir({TASK}) = {tc.task_dir(TASK)}")
    print("ok benchmark labels: every task dir has one (its BENCHMARKS prefix), in its benchmark's folder")


def caps(task: Path) -> list[str]:
    out = re.findall(r"(?m)^cpus\s*=\s*\S+", (task / "task.toml").read_text())
    for f in sorted((task / "environment").glob("*docker-compose.y*ml")):
        out += [m.strip() for m in re.findall(r"(?m)^[ \t]*cpus:[ \t]*\S+", f.read_text())]
    return out


def num(cap: str) -> float:
    return float(re.split(r"[=:]", cap)[1])


def test_clamp():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for t in (f"{BIG}-standard", HB, f"{SMALL}-standard"):
            shutil.copytree(tc.task_dir(t), td / t, symlinks=True)
        big, hb, small = td / f"{BIG}-standard", td / HB, td / f"{SMALL}-standard"
        check(max(num(c) for c in caps(big)) == 12 and max(num(c) for c in caps(hb)) == 16, "the fixtures' caps changed")
        r = subprocess.run(CLAMP + ["--cpus", "8", "--needs", str(small)], capture_output=True, text=True)
        check(r.returncode == 1 and not r.stdout, f"--needs on caps <= 8: {r.returncode} {r.stdout}")
        r = subprocess.run(CLAMP + ["--cpus", "8", "--needs", str(small), str(big)], capture_output=True, text=True)
        check(r.returncode == 0 and "12 -> 8" in r.stdout, f"--needs on a cap of 12: {r.returncode} {r.stdout}")
        check(caps(big) == caps(tc.task_dir(f"{BIG}-standard")), "--needs wrote something")
        before = {t: {p: p.read_bytes() for p in t.rglob("*") if p.is_file()} for t in (big, hb, small)}
        r = subprocess.run(CLAMP + ["--cpus", "8", str(big), str(hb), str(small)], capture_output=True, text=True)
        check(r.returncode == 0, f"clamp: {r.returncode} {r.stderr}")
        for t in (big, hb, small):
            orig = caps(tc.task_dir(t.name))
            got = caps(t)
            check(len(got) == len(orig) and all(num(g) == min(num(o), 8) for g, o in zip(got, orig)), f"{t.name}: {orig} -> {got}")
            for p, b in before[t].items():                     # only the cpus values changed, nothing else in any file
                a = p.read_bytes()
                if a != b:
                    strip = lambda x: re.sub(rb"(?m)^([ \t]*cpus[ \t]*[:=][ \t]*)\d+(?:\.\d+)?", rb"\1N", x)
                    check(strip(a) == strip(b), f"{p}: more than a cpus value changed")
        check(all(p.read_bytes() == b for p, b in before[small].items()), "a task without a cap above the host's was rewritten")
        check(subprocess.run(CLAMP + ["--cpus", "8", "--needs", str(big), str(hb)], capture_output=True).returncode == 1,
              "a clamped copy still needs clamping")
        orig = caps(tc.task_dir(HB))
        r = subprocess.run(CLAMP + ["--cpus", "8", str(tc.task_dir(HB))], capture_output=True, text=True)
        check(r.returncode != 0 and "copy" in r.stderr, f"clamping tasks/ itself was not refused: {r.returncode} {r.stderr}")
        check(caps(tc.task_dir(HB)) == orig and max(num(c) for c in orig) == 16, "tasks/ was clamped")


FAKE_HARBOR = r'''#!/usr/bin/env python3
import json, os, re, sys
a = sys.argv[1:]
tasks = [a[i + 1] for i, x in enumerate(a) if x == "-i"]
rec = {"cwd": os.getcwd(), "caps": {}, "unstamped": {}}
sys.path.insert(0, os.environ["RCB_SCRIPTS"])
import stamp_mtimes
for t in tasks:
    d = os.path.join(os.getcwd(), a[a.index("-p") + 1], t)
    rec["unstamped"][t] = stamp_mtimes.stamp_tree(d, check=True)["bad"]
    c = re.findall(r"(?m)^cpus\s*=\s*(\S+)", open(os.path.join(d, "task.toml")).read())
    c += re.findall(r"(?m)^[ \t]*cpus:[ \t]*([0-9.]+)", open(os.path.join(d, "environment", "docker-compose.yaml")).read())
    rec["caps"][t] = [float(x) for x in c]
with open(os.environ["FAKE_HARBOR_OUT"], "a") as f:
    f.write(json.dumps(rec) + "\n")
'''


def test_batch_runner():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td / "bin").mkdir()
        (td / "bin/harbor").write_text(FAKE_HARBOR); (td / "bin/harbor").chmod(0o755)
        rec = td / "harbor.jsonl"
        orig = {t: caps(tc.task_dir(t)) for t in (f"{BIG}-standard", f"{SMALL}-standard")}
        env = {**os.environ, "PATH": f"{td / 'bin'}:{os.environ['PATH']}", "FAKE_HARBOR_OUT": str(rec), "JOBS": str(td / "jobs"),
               "RESULTS": "", "LOG_MIRROR": "0", "MEM_GUARD": "0", "GATEWAY": "0", "WEB_SEARCH": "allowed", "MODES": "standard",
               "HOST_CPUS": "8", "RCB_SCRIPTS": str(ROOT / "scripts")}
        r = subprocess.run(["bash", str(ROOT / "scripts/run_agent_batch.sh"), "clamptest", BIG, SMALL], env=env,
                           capture_output=True, text=True, timeout=300)
        check(r.returncode == 0, f"run_agent_batch.sh exited {r.returncode}: {r.stderr[-800:]}")
        runs = [json.loads(l) for l in rec.read_text().splitlines()] if rec.exists() else []
        check(len(runs) == 2, f"harbor ran {len(runs)} times: {runs}")
        for run in runs:
            for t, c in run["caps"].items():
                check(c and max(c) <= 8, f"{t} ran with caps {c} on an 8-CPU host")
                # every job (GATEWAY=0 too, with or without a clamp) runs from its own copy, every file content-stamped (#258)
                base = BIG if t.startswith(BIG) else SMALL
                check(Path(run["cwd"]).resolve() == (td / f"jobs/.tasks/clamptest-standard-{base}").resolve(),
                      f"{t} ran from {run['cwd']}, not its job copy")
                check(run["unstamped"].get(t) == 0, f"{t}'s copy had {run['unstamped'].get(t)} file(s) without their content stamp")
        log = (td / "jobs/clamptest.log").read_text()
        check("clamped" in log and "12 -> 8" in log, "the clamp is not in the batch log")
        check(not any((td / f"jobs/.tasks/clamptest-standard-{b}").exists() for b in (BIG, SMALL)), "a job copy was not removed")
        for t, c in orig.items():
            check(caps(tc.task_dir(t)) == c, f"{tc.task_relpath(t)} was changed")


KILLER_HARBOR = r'''#!/usr/bin/env python3
import glob, os, signal, sys
a = sys.argv[1:]
jobs, job = a[a.index("-o") + 1], a[a.index("--job-name") + 1]
os.makedirs(os.path.join(jobs, job), exist_ok=True)
logs = sorted(glob.glob(os.path.join(jobs, ".gateway", "gateway-*.log")), key=os.path.getmtime)
with open(os.environ["FAKE_HARBOR_OUT"], "a") as f:
    f.write(job + " " + " ".join(os.path.basename(l) for l in logs) + "\n")
if not os.path.exists(os.environ["FAKE_HARBOR_OUT"] + ".killed"):     # the first job: the gateway dies under it
    open(os.environ["FAKE_HARBOR_OUT"] + ".killed", "w").close()
    os.kill(int(os.path.basename(logs[-1])[len("gateway-"):-len(".log")]), signal.SIGKILL)
'''


def test_gateway_restart():
    """Board 0121 M4: GATEWAY=1, the gateway killed during the first job: that job gets gateway_down.json (its trials are
    not results), the runner restarts the gateway on its port before the next job, and the next job runs."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td / "bin").mkdir()
        (td / "bin/harbor").write_text(KILLER_HARBOR); (td / "bin/harbor").chmod(0o755)
        rec = td / "harbor.txt"
        env = {**os.environ, "PATH": f"{td / 'bin'}:{os.environ['PATH']}", "FAKE_HARBOR_OUT": str(rec), "JOBS": str(td / "jobs"),
               "RESULTS": "", "LOG_MIRROR": "0", "MEM_GUARD": "0", "GATEWAY": "1", "GATEWAY_BIND": "127.0.0.1",
               "GATEWAY_EGRESS": "task", "WEB_SEARCH": "allowed", "MODES": "standard", "HOST_CPUS": "64"}
        r = subprocess.run(["bash", str(ROOT / "scripts/run_agent_batch.sh"), "gwtest", SMALL, "robotwin_2_0_place_a2b_left"],
                           env=env, capture_output=True, text=True, timeout=300)
        check(r.returncode == 0, f"run_agent_batch.sh (gateway) exited {r.returncode}: {r.stderr[-800:]}")
        runs = rec.read_text().splitlines() if rec.exists() else []
        check(len(runs) == 2, f"harbor ran {len(runs)} times: {runs}")
        log = (td / "jobs/gwtest.log").read_text()
        check("restarting it on port" in log and "usage gateway restarted" in log, f"no gateway restart in the log: {log[-1500:]}")
        check((td / f"jobs/gwtest-standard-{SMALL}/gateway_down.json").exists(), "the job the gateway died in has no gateway_down.json")
        check(not (td / "jobs/gwtest-standard-robotwin_2_0_place_a2b_left/gateway_down.json").exists(),
              "the job after the restart has a gateway_down.json")
        pids = {l.split()[-1] for l in runs}
        check(len(pids) == 2, f"the second job did not run behind a new gateway: {runs}")


if __name__ == "__main__":
    test_results()
    test_config_and_attempts()
    test_summary_grouping()
    test_core_set()
    test_benchmarks()
    test_clamp()
    test_batch_runner()
    test_gateway_restart()
    if fails:
        print(f"{len(fails)} failure(s)")
        sys.exit(1)
    print("ok: write_task_results not-a-result cases, config.json and attempts, the summary per configuration, the core set, clamp_cpus, run_agent_batch.sh stamped job copies, clamped copies and gateway restart")
