#!/usr/bin/env python3
"""Collect a two-mode batch (unlimited + limited Harbor jobs) into a results folder: per task and mode the verifier's
replay.mp4 / replay.last.png / reward.json plus agent cost, and a summary.md table.
usage: collect_batch_results.py <jobs_dir> <unlimited_job> <limited_job> <out_dir> [<oracle_job_unlimited> <oracle_job_limited>]
TopoGym (adapted from robot_coding_bench fa59c1a6): topogym-* trials and a neutral title."""
import json, pathlib, shutil, sys, datetime as dt
from helper_assignment import planned_trials
from topogym_versions import bound_release


ARTIFACT_CONTRACT_VERSION = 2
OPTIONAL_DIAGNOSTICS = ("submission_error.json", "instance_error.json")


def result_artifacts(mode, *, media=True):
    """Ordered verifier evidence shared by collection and HF export.

    The recording manifest follows the files it references so exports can update
    hashes after JSONL sanitization. Historical runs may lack the new sidecars.
    """
    if not media:
        return ("reward.json",)
    verdicts = (("verdict.json", "media.json", *OPTIONAL_DIAGNOSTICS)
                if mode == "unlimited" else ("final.json", "replay.verdict.json"))
    return ("reward.json", "replay.mp4", "replay.last.png", "trajectory.npz", "episode.jsonl",
            *verdicts, "replay.frame_map.jsonl", "replay.recording_manifest.json")


def load_json(path):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def artifact_source(trial, mode, name):
    """Use Harbor's submitted trajectory for unlimited, verifier evidence otherwise."""
    relative = pathlib.Path("artifacts/app/output" if mode == "unlimited" and name == "trajectory.npz" else "verifier") / name
    src = trial
    if src.is_symlink():
        return None
    for part in relative.parts:
        src = src / part
        if src.is_symlink():
            return None
    return src if src.is_file() else None


def classify_trial(job, row, mode):
    """Only a finished trial + verifier evidence counts as completion, not job/result.json."""
    results = sorted(job.glob("*/result.json"))
    if not results:
        return ("interrupted" if job.exists() else "pending"), {}, {}, None
    if len(results) != 1:
        return "invalid_job", {}, {}, None
    result = load_json(results[0])
    trial = results[0].parent
    expected = {row["slug"] + ("-limited" if mode == "limited" else ""),
                row["slug"] + ("-standard" if mode == "limited" else "-privileged")}
    if (result.get("task_name") or "").split("/")[-1] not in expected:
        return "identity_mismatch", result, {}, trial
    reward = load_json(trial / "verifier/reward.json")
    from account_failure_check import check as account_failure
    if account_failure(str(trial))["stop"]:
        return "infra_failed", result, reward, trial
    exception = (result.get("exception_info") or {}).get("exception_type")
    if exception in {"CancelledError", "KeyboardInterrupt"} or not result.get("finished_at"):
        return "interrupted", result, reward, trial
    if exception and exception not in {"AgentTimeoutError", "AgentTimeout"}:
        return "infra_failed", result, reward, trial
    verifier = result.get("verifier_result") or {}
    if not verifier.get("rewards") or reward.get("success") not in (0, 1):
        return "infra_failed", result, reward, trial
    if (any(reward.get(key) for key in ("grader_error", "missing_log", "infra_error", "gpu_lost"))
            or (mode == "limited" and not reward.get("finalized"))):
        return "infra_failed", result, reward, trial
    if any(reward.get(key) for key in ("missing_trajectory", "bad_trajectory", "wrong_family")):
        return "invalid_submission", result, reward, trial
    if reward.get("instance_mismatch") or not row["evaluable_for_task_success"]:
        return "not_evaluable", result, reward, trial
    if bound_release(row.get("tooling_version")) and reward["success"] == 1 and reward.get("runtime_binding_ok") != 1:
        return "not_evaluable", result, reward, trial
    if reward.get("success_pending_review") == 1:
        # The physical-validity policy (tooling v16): a success with a deep task contact is held for a human review, neither
        # credited nor failed; the verifier saved the events and frames (verdict.json evidence.review / review.json).
        return "pending_review", result, reward, trial
    return ("solved" if reward["success"] == 1 else "unsolved"), result, reward, trial


def manifest_rows(manifest, jobs, run, *, copy_artifacts=False):
    """Read classifications without rewriting the received evidence."""
    from helper_assignment import atomic_json
    rows = []
    for sample, mode in planned_trials(manifest):
        stem = f"d{sample['task_number']:02d}-{sample['difficulty']}-{sample['sample_id']}-{mode}"
        # Explicit mapping from manifest; never infer task identity from truncated trial folders.
        attempts = sorted(jobs.glob(stem + "-a[0-9][0-9][0-9]")) or [jobs / (stem + "-a001")]
        for job in attempts:
            status, result, reward, trial = classify_trial(job, sample, mode)
            if status == "pending" and not (run / "build" / sample["slug"] / "preflight.ok.json").exists():
                status = "blocked_preflight"
            agent = result.get("agent_result") or {}
            row = dict(task_id=sample["task_id"], difficulty=sample["difficulty"], sample_id=sample["sample_id"],
                       scene_seed=sample["scene_seed"], mode=mode, trial=1,
                       tooling_version=sample.get("tooling_version", "historical_unrecorded"),
                       release_definition_sha256=sample.get("release_definition_sha256"),
                       environment_profile=sample.get("environment_profile"), attempt=int(job.name[-3:]),
                       status=status, success=reward.get("success"),
                       evaluable_for_task_success=sample["evaluable_for_task_success"],
                       tokens_in=agent.get("n_input_tokens"), tokens_out=agent.get("n_output_tokens"),
                       cost_usd_api_price=agent.get("cost_usd"), exception=(result.get("exception_info") or {}).get("exception_type"),
                       job=str(job), harbor_trial=str(trial) if trial else None)
            rows.append(row)
            if trial and copy_artifacts:
                target = run / "results" / sample["task_id"] / sample["difficulty"] / sample["sample_id"] / mode / "trial_01" / f"attempt_{row['attempt']:03d}"
                target.mkdir(parents=True, exist_ok=True)
                for name in result_artifacts(mode):
                    src = artifact_source(trial, mode, name)
                    if src is not None:
                        dest = target / name
                        if not dest.exists() or src.stat().st_size != dest.stat().st_size or src.stat().st_mtime > dest.stat().st_mtime:
                            shutil.copy2(src, dest)
                atomic_json(target / "agent_summary.json", row)
    return rows


def collect_manifest(manifest_path, jobs, *, copy_artifacts=True):
    import csv
    manifest_path, jobs = pathlib.Path(manifest_path).resolve(), pathlib.Path(jobs).resolve()
    run = manifest_path.parent
    manifest = json.loads(manifest_path.read_text())
    rows = manifest_rows(manifest, jobs, run, copy_artifacts=copy_artifacts)
    temp = run / "trials.jsonl.tmp"
    temp.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    temp.replace(run / "trials.jsonl")
    with (run / "summary.csv.tmp").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    (run / "summary.csv.tmp").replace(run / "summary.csv")
    counts = {status: sum(r["status"] == status for r in rows) for status in sorted({r["status"] for r in rows})}
    latest = {}
    for row in rows:
        key = (row["task_id"], row["difficulty"], row["sample_id"], row["mode"])
        if key not in latest or row["attempt"] > latest[key]["attempt"]:
            latest[key] = row
    eligible = [r for r in latest.values() if r["status"] in {"solved", "unsolved"}]
    lines = ["# Difficulty evaluation", "", "Release: " + json.dumps(manifest.get("release", {"name": "historical_unrecorded"}), sort_keys=True), "", f"Planned trials: {manifest['trial_count']}; observed attempt rows: {len(rows)}.", "",
             f"Evaluable completed trials (latest attempt each): {sum(r['status'] == 'solved' for r in eligible)}/{len(eligible)} solved.",
             "Not-evaluable, invalid submissions and infrastructure failures are excluded from this denominator.",
             f"Held for review (a success with a deep task contact, credited only after review): "
             f"{sum(r['status'] == 'pending_review' for r in latest.values())}.", "",
             "| task | difficulty | sample | mode | attempt | status |", "|---|---|---|---|---|---|"]
    lines += [f"| {r['task_id']} | {r['difficulty']} | {r['sample_id']} | {r['mode']} | {r['attempt']} | {r['status']} |" for r in rows]
    (run / "summary.md.tmp").write_text("\n".join(lines) + "\n")
    (run / "summary.md.tmp").replace(run / "summary.md")
    print(json.dumps(counts, sort_keys=True))
    return 0 if all(r["status"] in {"solved", "unsolved", "pending_review", "not_evaluable", "invalid_submission"}
                    for r in latest.values()) else 2
def legacy_main():
    jobs, ju, jl, out = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3], pathlib.Path(sys.argv[4])
    from regrade_trials import original_task
    release_ids = set()
    for job in (ju, jl):
        for result_path in (jobs/job).glob("*/result.json"):
            try:
                record = json.loads((original_task(result_path.parent)/"task_release.json").read_text())["release"]
                release_ids.add(record["definition_sha256"])
            except (OSError, ValueError, KeyError):
                release_ids.add("historical_unrecorded")
    if len(release_ids) > 1:
        raise ValueError("Input jobs use different releases; collect them separately")
    out.mkdir(parents=True, exist_ok=True)
    def span(x):
        try:
            a=dt.datetime.fromisoformat(x["started_at"].replace("Z","+00:00")); b=dt.datetime.fromisoformat(x["finished_at"].replace("Z","+00:00")); return round((b-a).total_seconds())
        except Exception: return None
    rows={}
    for mode, job in (("unlimited", ju), ("limited", jl)):
        for trial in sorted((jobs/job).glob("topogym-*")):
            if not trial.is_dir(): continue
            r=json.load(open(trial/"result.json")) if (trial/"result.json").exists() else {}
            name=(r.get("task_name") or trial.name.split("__")[0]).split("/")[-1].replace("topogym-","").replace("-limited","")  # dir names are truncated
            rw=json.load(open(trial/"verifier/reward.json")) if (trial/"verifier/reward.json").exists() else {}
            ar=r.get("agent_result") or {}
            d=out/name/mode; d.mkdir(parents=True, exist_ok=True)
            for f in result_artifacts(mode):
                src = artifact_source(trial, mode, f)
                if src is not None: shutil.copy(src, d/f)
            for f in ("gen.py",):
                src=trial/"artifacts/app/output"/f
                if src.exists(): shutil.copy(src, d/f)
            info={"release_definition_sha256": next(iter(release_ids), "historical_unrecorded"), "success": rw.get("success"), "agent_s": span(r.get("agent_execution") or {}), "verifier_s": span(r.get("verifier") or {}),
                  "tokens_in": ar.get("n_input_tokens"), "tokens_out": ar.get("n_output_tokens"), "cost_usd_api_price": ar.get("cost_usd"),
                  "n_actions": rw.get("n_actions"), "sim_steps": rw.get("sim_steps"), "steps": rw.get("steps"),
                  "agent_resets": rw.get("agent_resets"), "agent_sim_steps": rw.get("agent_sim_steps"),
                  "exception": ((r.get("exception_info") or {}).get("exception_type")), "trial": str(trial)}
            json.dump(info, open(d/"agent_summary.json","w"), indent=1)
            prev=rows.setdefault(name,{}).get(mode)
            if prev and (prev.get("started_at") or "") > (r.get("started_at") or ""):   # several trials of one task: keep the latest
                continue
            info["started_at"]=r.get("started_at"); rows[name][mode]=info
    L=[f"# TopoGym — unlimited vs limited\n", f"Collected {dt.date.today().isoformat()} from `{ju}` and `{jl}`. Videos and rewards per task under `<task>/<mode>/`.\n",
       "| task | unlimited | agent s | tokens in/out | actions | limited | agent s | tokens in/out | actions |","|---|---|---|---|---|---|---|---|---|"]
    def cell(i):
        if not i: return "—","","",""
        s={1:"✅ 1",0:"❌ 0"}.get(i.get("success"), "⚠ err" if i.get("exception") else "?")
        return s, str(i.get("agent_s") or ""), f"{(i.get('tokens_in') or 0)/1000:.0f}k / {(i.get('tokens_out') or 0)/1000:.1f}k", str(i.get("n_actions") or i.get("steps") or "")
    tot={"unlimited":[0,0],"limited":[0,0]}
    for name in sorted(rows):
        u,l=rows[name].get("unlimited"),rows[name].get("limited")
        for m,i in (("unlimited",u),("limited",l)):
            if i: tot[m][1]+=1; tot[m][0]+=int(i.get("success")==1)
        cu,cl=cell(u),cell(l); L.append(f"| {name} | {cu[0]} | {cu[1]} | {cu[2]} | {cu[3]} | {cl[0]} | {cl[1]} | {cl[2]} | {cl[3]} |")
    L.append(f"\n**Totals:** unlimited {tot['unlimited'][0]}/{tot['unlimited'][1]} · limited {tot['limited'][0]}/{tot['limited'][1]}\n")
    (out/"summary.md").write_text("\n".join(L)); print("\n".join(L))


if __name__ == '__main__':
    if '--manifest' in sys.argv:
        import argparse
        parser = argparse.ArgumentParser(description='Collect every planned difficulty trial and attempt, including missing/interrupted ones.')
        parser.add_argument('--manifest', required=True)
        parser.add_argument('--jobs-dir', required=True)
        args = parser.parse_args()
        raise SystemExit(collect_manifest(args.manifest, args.jobs_dir))
    legacy_main()
