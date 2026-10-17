#!/usr/bin/env python3
"""Write per-task agent results for the results site (not into the repository, PROTOCOL D3): <out>/<task>/<run id>/README.md
(+ replay.mp4, replay.last.png, config.json, attempts.json). One folder per agent+model; the privileged and standard twins
each get their own.
usage: write_task_results.py <jobs_dir> <job_name> <run-id> "<agent label>" --out <dir> [--analysis <a Python file with ANALYSIS = {family: {"U": text, "L": text}}>]

config.json (RUNNING.md "Results", PROTOCOL v2.0): the trial's effective configuration (scripts/task_conventions.py
effective_config: protocol version, mode, cutoff, reset budget, slowdown S, seed, network, validated flag, digest), its
result (`success`, `fail` or `not_a_result` with the reason) and whether it is counted. Results are ranked only within
one comparable configuration (task_conventions.config_key), validated and unvalidated tasks together.
attempts.json: every trial of this task x run id seen so far. RUNNING.md "Infrastructure retry": an infrastructure failure
(not a result) allows at most one full retry with the same instance, seed and configuration; the voided attempt is never
counted, an agent's own failure is never retried, and more than 2 attempts of one task x run id is flagged
(`attempts_over_cap`)."""
import json, pathlib, shutil, sys, re, glob, datetime as dt, ast
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent)); from task_names import base, canonical, mode as mode_of  # noqa: E402
import account_failure_check  # noqa: E402
import task_conventions as tc  # noqa: E402
import retry_policy as rp  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
MAX_ATTEMPTS = 1 + rp.MAX_INFRA_RETRIES   # PROTOCOL Appendix H.5: the first attempt and at most one retry after an infrastructure failure
OUTCOME = {"not_a_result": "infra_failure", "success": "success"}   # anything else: the agent's failure (a result)
OVERRIDES = ("RCB_RESET_BUDGET", "RCB_SLOWDOWN")   # run-time overrides of a task's declared settings (PROTOCOL §2)


def span(x):
    try:
        a = dt.datetime.fromisoformat(x["started_at"].replace("Z", "+00:00")); b = dt.datetime.fromisoformat(x["finished_at"].replace("Z", "+00:00")); return round((b - a).total_seconds())
    except Exception: return None


def last_msgs(trial, k=3):
    try:
        d = json.load(open(glob.glob(str(trial / "agent/trajectory.json"))[0]))
        return [s["message"].strip().replace("\n", " ") for s in d.get("steps", []) if s.get("source") == "agent" and (s.get("message") or "").strip()][-k:]
    except Exception: return []


NOT_A_RESULT = "**not a result** — infrastructure error ({}): run it again; it is not the agent's 0"


def not_a_result(trial, r, rw):
    """Why a trial that is not a success is no result either (PROTOCOL §2.6, §2.12: an infrastructure failure is neither a
    success nor the agent's 0; only the agent's own end, its deliverable or the cutoff, AgentTimeoutError, is a result),
    or None. Board 0105 F-M2: a trial whose verifier never ran (no reward.json: `docker compose up` failed, e.g. a CPU
    cap above the host's; the verifier timed out) was published as the agent's 0."""
    if rw.get("infra_error") or rw.get("grader_error"):
        return "`infra_error` / `grader_error` in the verifier line"
    ex = (r.get("exception_info") or {}).get("exception_type") or ""
    if not rw:
        return "the verifier wrote no reward.json" + (f"; Harbor: `{ex}`" if ex else "")
    if ex and ex != "AgentTimeoutError":
        return f"Harbor ended the trial with `{ex}`"
    try:
        chk = account_failure_check.check(str(trial))
        if chk.get("stop") and not any(w.startswith("gateway:") for w in chk.get("why", [])):
            return "a model-account or configuration failure (scripts/account_failure_check.py)"
        # board 0121 M4: the usage gateway died, or the trial's last model calls failed on the way (upstream unreachable,
        # a stream broken off, a provider 5xx): the agent could not reach its model
        gw = [w for w in chk.get("infra", []) if w.startswith("gateway:")]
        if gw:
            return "the model API could not be reached through the usage gateway (" + gw[0].removeprefix("gateway: ") + ")"
    except Exception:
        pass
    return None


def load_json(p):
    try:
        d = json.load(open(p))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def load_reward(trial):
    return load_json(trial / "verifier/reward.json")


def classify(trial, r, rw):
    """(status, reason, over the token budget): status `success`, `fail` (the agent's own result, counted) or
    `not_a_result` (infrastructure: voided, never counted)."""
    gw = load_json(trial / "gateway/totals.json")
    over = bool(gw.get("over_token_budget"))               # PROTOCOL §5: over the token budget = failed
    # PROTOCOL §2.6: infra_error (or a grader error) = not a result, neither a success nor the agent's 0; so is a trial
    # the verifier never graded, or that Harbor or the model account ended (not_a_result). A verdict of success with no
    # infrastructure flag stands; over the token budget is the agent's failure unless the verifier flagged infrastructure.
    infra = bool(rw.get("infra_error") or rw.get("grader_error"))
    ok = rw.get("success") == 1 and not over and not infra
    why = None if ok or (over and not infra) else not_a_result(trial, r, rw)
    return ("success" if ok else "not_a_result" if why else "fail"), why, over


def trial_config(trial, task, r):
    """The trial's effective configuration (task_conventions.effective_config) with how its seed is known. The seed: the
    runner's copy of the task the trial ran from (scripts/task_seed.py materialize writes the chosen seed as its
    `[metadata.seeds] default`), else the task's default seed (`seed_source = "default"`). Run-time overrides: the trial's
    recorded environment. A trial of another version of the task (its `task_checksum` is not the task's DIGEST now) keeps
    only what its name says; the rest is "legacy"."""
    tdir = ROOT / "tasks" / task
    hc = load_json(trial / "config.json")
    env = {}
    for src in ((hc.get("environment") or {}).get("env"), (hc.get("agent") or {}).get("env"), hc.get("env")):
        if isinstance(src, dict):
            env.update({k: str(v) for k, v in src.items() if k in OVERRIDES})
    seed, source = None, "default"
    p = ((hc.get("task") or {}).get("path") or "")
    if p:
        copy = pathlib.Path(p) if pathlib.Path(p).is_absolute() else ROOT / p
        if copy.resolve() != tdir.resolve() and (copy / "task.toml").is_file():
            try:
                seed, source = tc.seeds_of(tc.metadata_of(copy))["default"], "runner copy"
            except (ValueError, KeyError, TypeError):
                pass
    cfg = tc.effective_config(tdir, seed=seed, env=env)
    cfg["seed_source"] = source
    want = (r.get("task_checksum") or "").removeprefix("sha256:")
    have = cfg.get("digest", "").removeprefix("sha256:")
    cfg["digest_match"] = (want == have) if want and have else None
    if cfg["digest_match"] is False and source == "default":   # another version of the task: only the name is known
        for k in ("cutoff_s", "reset_budget", "slowdown", "seed", "network", "validated", "oracle", "service_protocol"):
            cfg[k] = "legacy"
        cfg["protocol_version"] = "legacy"
        cfg["digest"] = "sha256:" + want
    return cfg


def started(r):
    return r.get("started_at") or ""


def record_attempt(out, trial, r, status):
    """attempts.json in the task's result folder: every trial of this task x run id, oldest first."""
    f = out / "attempts.json"
    led = load_json(f).get("attempts", [])
    key = r.get("id") or trial.name
    led = [a for a in led if a.get("id") != key]
    led.append({"id": key, "trial": trial.name, "job": trial.parent.name, "started_at": started(r), "status": status,
                "counted": status != "not_a_result"})
    led.sort(key=lambda a: a.get("started_at") or "")
    f.write_text(json.dumps({"attempts": led}, indent=1) + "\n")
    return led


def main(argv):
    jobs, job, slug, label = pathlib.Path(argv[1]), argv[2], argv[3], argv[4]
    if "--out" not in argv: sys.exit("--out <dir> is required: results are published on the results site, not committed (PROTOCOL D3)")
    out_root = pathlib.Path(argv[argv.index("--out") + 1]).resolve()
    if out_root == ROOT or ROOT in out_root.parents: sys.exit("--out must be outside the repository (PROTOCOL D3)")
    analysis = {}
    if "--analysis" in argv:
        src = pathlib.Path(argv[argv.index("--analysis") + 1]).read_text()
        m = re.search(r"ANALYSIS = (\{.*?\n\})\n", src, re.S)
        if m: analysis = ast.literal_eval(m.group(1))
    n = 0
    trials = []
    for trial in (jobs / job).glob("*__*"):
        if (trial / "result.json").exists():
            trials.append((trial, json.load(open(trial / "result.json"))))
    for trial, r in sorted(trials, key=lambda tr: (started(tr[1]), tr[0].name)):
        task = canonical(r["task_name"].split("/")[-1])   # also pre-v1.0 jobs
        tdir = ROOT / "tasks" / task
        if not tdir.is_dir(): continue
        rw = load_reward(trial)
        ar = r.get("agent_result") or {}; mode = mode_of(task); limited = mode != "privileged"; fam = base(task).replace("robotwin_2_0_", "")
        out = out_root / task / slug; out.mkdir(parents=True, exist_ok=True)
        status, why, over = classify(trial, r, rw)
        led = record_attempt(out, trial, r, status)
        rule = rp.check_attempts([{"outcome": OUTCOME.get(a["status"], "agent_failure")} for a in led])
        over_cap = bool(rule)
        if over_cap:
            print(f"WARN {task} / {slug}: {len(led)} attempts break the retry rule (PROTOCOL Appendix H.5, at most "
                  f"{MAX_ATTEMPTS}: one retry after an infrastructure failure): {'; '.join(rule)}")
        counted = [a for a in led if a["counted"]]
        if status == "not_a_result" and counted:
            # a voided attempt never replaces a counted one: it is recorded in attempts.json only
            print(f"{task} / {slug}: trial {trial.name} is not a result (voided); the counted attempt stays")
            continue
        cfg = trial_config(trial, task, r)
        cfg.update({"run_id": slug, "job": job, "trial": trial.name, "result": status, "not_a_result_reason": why,
                    "counted": status != "not_a_result", "attempts": len(led), "attempts_over_cap": over_cap})
        (out / "config.json").write_text(json.dumps(cfg, indent=1) + "\n")
        for f in ("replay.mp4", "replay.last.png"):
            if (trial / "verifier" / f).exists(): shutil.copy(trial / "verifier" / f, out / f)
        ok = status == "success"
        an = analysis.get(fam, {}).get("L" if limited else "U", "")
        lines = [f"# {label} — {task}\n",
                 f"Run: Harbor job `{job}`, trial `{trial.name}`, {(r.get('started_at') or '')[:10]}. Mode: **{ {'standard': 'standard (robot as a service)', 'standard-realtime': 'standard-realtime (robot as a service, time does not stop)'}.get(mode, 'privileged')}**.\n",
                 "| | |", "|---|---|",
                 f"| result | {'**1 (success)**' if ok else NOT_A_RESULT.format(why) if why else '**0**' + (' — over the token budget' if over else ' — no trajectory handed in' if rw.get('missing_trajectory') else '')} |",
                 f"| configuration | {tc.config_label(cfg)}; seed {cfg.get('seed')} ({cfg.get('seed_source')}); "
                 f"{'validated' if cfg.get('validated') is True else 'unvalidated' if cfg.get('validated') is False else 'legacy'}"
                 f"{'; easy set (docs/easy_set.toml)' if cfg.get('set') == 'easy' else ''} (`config.json`) |",
                 f"| attempts | {len(led)}" + (f" — **over the cap of {MAX_ATTEMPTS}**" if over_cap else "") + " |",
                 f"| agent time | {span(r.get('agent_execution') or {})} s |",
                 f"| actions / physics steps | {rw.get('steps') or rw.get('n_actions') or '—'} / {rw.get('sim_steps') or '—'} |",
                 f"| tokens in / out | {ar.get('n_input_tokens')} / {ar.get('n_output_tokens')} |",
                 f"| verifier | `{json.dumps({k: v for k, v in rw.items() if k not in ('agent_sessions','agent_records','agent_replays')})}` |",
                 f"| verifier sandbox | {r.get('verifier_environment_mode')} |\n"]
        if not limited and rw.get("agent_resets") is not None:
            lines.append(f"Debugging footprint (self-reported by the agent's tooling log): {rw.get('agent_sessions')} sessions, {rw.get('agent_resets')} resets, {rw.get('agent_sim_steps')} physics steps.\n")
        if (out / "replay.mp4").exists():
            lines += ["## Replay (verifier's six-camera video)\n", f"![last frame](replay.last.png)\n", "[replay.mp4](replay.mp4) — top: world / observer / head; bottom: front / left wrist / right wrist.\n"]
        if an:
            lines += ["## Analysis\n", an + "\n"]
        msgs = last_msgs(trial)
        if msgs:
            lines += ["## Agent's last messages\n"] + [f"- {m[:600]}" for m in msgs] + [""]
        (out / "README.md").write_text("\n".join(lines)); n += 1
    print(f"{job}: wrote {n} result folders for {slug}")


if __name__ == "__main__":
    main(sys.argv)
