#!/usr/bin/env python3
"""Runner-side tools of board 0105 (F-M2), standard library and bash only:

- scripts/write_task_results.py publishes a trial the verifier never graded (no reward.json), one Harbor ended with an
  exception other than the agent's cutoff (AgentTimeoutError), or one stopped by a model-account failure as "not a
  result", never as the agent's 0; a verdict, the cutoff and the token budget stay results;
- scripts/clamp_cpus.py clamps every CPU cap of a task copy to the host's count (PROTOCOL §2.10) and nothing else, and
  refuses the repository's own tasks;
- scripts/run_agent_batch.sh runs a task whose cap is above HOST_CPUS from a clamped copy (a stand-in `harbor` on PATH
  records what it was given), runs a task without such a cap from tasks/ as before, and leaves tasks/ unchanged."""
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
TASK = "robotwin_2_0_stack_blocks_two-standard"          # any task of the repository (write_task_results looks it up)
BIG = "behavior-boxing-food-after-dinner-i00"             # its standard twin's sidecar caps are 12 CPUs
HB = "humanoidbench-loco-walk-i00-privileged"            # [environment] cpus = 16
SMALL = "robotwin_2_0_stack_blocks_two"                  # caps of at most 8
fails = []


def check(cond, what):
    if not cond:
        fails.append(what)
        print("FAIL", what)


def result_line(td: Path, result: dict, reward=None, gateway=None, codex=None) -> str:
    jobs = td / "jobs"; job = f"j{len(list(jobs.glob('*'))) if jobs.exists() else 0}"
    trial = jobs / job / f"{TASK}__abc"
    trial.mkdir(parents=True)
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
        for name, result, reward, gateway, codex, want in cases:
            line = result_line(td, result, reward, gateway, codex)
            check(want in line, f"write_task_results: {name}: {line}")
            if want != "not a result":
                check("not a result" not in line, f"write_task_results: {name} is a result: {line}")
        line = result_line(td, {"exception_info": {"exception_type": "EnvironmentStartTimeoutError"}})
        check("EnvironmentStartTimeoutError" in line and "no reward.json" in line, f"the reason names Harbor's exception: {line}")


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
            shutil.copytree(ROOT / "tasks" / t, td / t, symlinks=True)
        big, hb, small = td / f"{BIG}-standard", td / HB, td / f"{SMALL}-standard"
        check(max(num(c) for c in caps(big)) == 12 and max(num(c) for c in caps(hb)) == 16, "the fixtures' caps changed")
        r = subprocess.run(CLAMP + ["--cpus", "8", "--needs", str(small)], capture_output=True, text=True)
        check(r.returncode == 1 and not r.stdout, f"--needs on caps <= 8: {r.returncode} {r.stdout}")
        r = subprocess.run(CLAMP + ["--cpus", "8", "--needs", str(small), str(big)], capture_output=True, text=True)
        check(r.returncode == 0 and "12 -> 8" in r.stdout, f"--needs on a cap of 12: {r.returncode} {r.stdout}")
        check(caps(big) == caps(ROOT / "tasks" / f"{BIG}-standard"), "--needs wrote something")
        before = {t: {p: p.read_bytes() for p in t.rglob("*") if p.is_file()} for t in (big, hb, small)}
        r = subprocess.run(CLAMP + ["--cpus", "8", str(big), str(hb), str(small)], capture_output=True, text=True)
        check(r.returncode == 0, f"clamp: {r.returncode} {r.stderr}")
        for t in (big, hb, small):
            orig = caps(ROOT / "tasks" / t.name)
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
        orig = caps(ROOT / "tasks" / HB)
        r = subprocess.run(CLAMP + ["--cpus", "8", str(ROOT / "tasks" / HB)], capture_output=True, text=True)
        check(r.returncode != 0 and "copy" in r.stderr, f"clamping tasks/ itself was not refused: {r.returncode} {r.stderr}")
        check(caps(ROOT / "tasks" / HB) == orig and max(num(c) for c in orig) == 16, "tasks/ was clamped")


FAKE_HARBOR = r'''#!/usr/bin/env python3
import json, os, re, sys
a = sys.argv[1:]
tasks = [a[i + 1] for i, x in enumerate(a) if x == "-i"]
rec = {"cwd": os.getcwd(), "caps": {}}
for t in tasks:
    d = os.path.join(os.getcwd(), a[a.index("-p") + 1], t)
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
        orig = {t: caps(ROOT / "tasks" / t) for t in (f"{BIG}-standard", f"{SMALL}-standard")}
        env = {**os.environ, "PATH": f"{td / 'bin'}:{os.environ['PATH']}", "FAKE_HARBOR_OUT": str(rec), "JOBS": str(td / "jobs"),
               "RESULTS": "", "LOG_MIRROR": "0", "MEM_GUARD": "0", "GATEWAY": "0", "WEB_SEARCH": "allowed", "MODES": "standard",
               "HOST_CPUS": "8"}
        r = subprocess.run(["bash", str(ROOT / "scripts/run_agent_batch.sh"), "clamptest", BIG, SMALL], env=env,
                           capture_output=True, text=True, timeout=300)
        check(r.returncode == 0, f"run_agent_batch.sh exited {r.returncode}: {r.stderr[-800:]}")
        runs = [json.loads(l) for l in rec.read_text().splitlines()] if rec.exists() else []
        check(len(runs) == 2, f"harbor ran {len(runs)} times: {runs}")
        for run in runs:
            for t, c in run["caps"].items():
                check(c and max(c) <= 8, f"{t} ran with caps {c} on an 8-CPU host")
                if t.startswith(BIG):
                    check(Path(run["cwd"]).resolve() == (td / "jobs/.tasks/clamptest-standard-" f"{BIG}").resolve(),
                          f"the clamped task ran from {run['cwd']}, not its job copy")
                else:
                    check(Path(run["cwd"]).resolve() == ROOT.resolve(), f"a task without a cap above the host's ran from {run['cwd']}")
        log = (td / "jobs/clamptest.log").read_text()
        check("clamped" in log and "12 -> 8" in log, "the clamp is not in the batch log")
        check(not (td / f"jobs/.tasks/clamptest-standard-{BIG}").exists(), "the job copy was not removed")
        for t, c in orig.items():
            check(caps(ROOT / "tasks" / t) == c, f"tasks/{t} was changed")


if __name__ == "__main__":
    test_results()
    test_clamp()
    test_batch_runner()
    if fails:
        print(f"{len(fails)} failure(s)")
        sys.exit(1)
    print("ok: write_task_results not-a-result cases, clamp_cpus, run_agent_batch.sh clamped copies")
