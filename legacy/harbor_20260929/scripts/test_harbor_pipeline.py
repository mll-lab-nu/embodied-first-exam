#!/usr/bin/env python3
"""Explicit Docker/GPU/API acceptance, using the same frozen tasks and native Job."""
import argparse
import json
import hashlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harbor_runners.collect import atomic_json
from harbor_runners.agents.credentials import redact
from harbor_runners.config import load_config
from harbor_runners.run import launch, apply_usage_args, input_key, new_run_id
from harbor_runners.task_generator import prepare


ISOLATION_CHECK = r'''
import json, os, pathlib, subprocess, tempfile, threading, time
from topogym.agents.rollout.policy_process import RemotePolicyProxy, PolicyCancelled
pathlib.Path('/trial/secret').write_text('manager private')
pathlib.Path('/home/agent/secret').write_text('agent credential marker')
os.chown('/home/agent/secret',10001,10001)
os.chmod('/home/agent/secret',0o600)
source = """import os, socket
class Policy:
 def act(self, obs):
  assert os.getuid()==10002
  assert not any('KEY' in key or 'TOKEN' in key for key in os.environ)
  for path in ['/trial/secret','/home/agent/secret']:
   try: open(path).read()
   except PermissionError: pass
   else: raise AssertionError('private file readable')
  try: socket.socket()
  except PermissionError: pass
  else: raise AssertionError('network allowed')
  try: open('/rollout/forged.json','w')
  except PermissionError: pass
  else: raise AssertionError('public evidence writable')
  return None
def create_policy(): return Policy()
"""
proxy=RemotePolicyProxy(dict(source_utf8=source,parameters={}), '/trial/probe')
try: assert proxy.act({}) is None
finally: proxy.close()
hang='import time\nclass P:\n def act(self, obs): time.sleep(100)\ndef create_policy(): return P()'
proxy=RemotePolicyProxy(dict(source_utf8=hang,parameters={}), '/trial/hang')
thread=threading.Timer(.5, proxy.cancel); thread.start()
start=time.monotonic()
try:
 proxy.act({})
 raise AssertionError('expected cancellation')
except PolicyCancelled: pass
finally: proxy.close(); thread.join()
assert time.monotonic()-start<5
for user in ['agent','policy']:
 result=subprocess.run(['runuser','-u',user,'--','cat','/trial/secret'],capture_output=True)
 assert result.returncode != 0
print(json.dumps({'uid_boundary':True,'private_files':True,'network_denied':True,'cancel':True}))
'''


def source_identity():
    files = {ROOT / 'scripts/test_harbor_pipeline.py', ROOT / 'tests/fixtures/cube_transfer.py',
        ROOT / 'tests/fixtures/cube_pick_place.py', ROOT / 'topogym/planning/examples/cube_pick_place.py'}
    for directory in ('topogym/agents/usage', 'topogym/agents/rollout', 'harbor_runners'):
        files.update((ROOT / directory).rglob('*.py'))
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(files) if path.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=["isolation", "scripted", "invalid", "cancel", "api", "sweep",
        "pick-cube-scripted", "pick-cube", "budget-input", "budget-output"], required=True)
    parser.add_argument("--image", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--model-name", "--model", dest="model")
    credentials = parser.add_mutually_exclusive_group()
    credentials.add_argument("--api-key")
    credentials.add_argument("--api-key-stdin", action="store_true")
    parser.add_argument("--env-file", type=Path, help="Private dotenv file; default: .secrets/harbor.env")
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--timeout-sec", type=int, default=1800)
    parser.add_argument("--gpu-devices", nargs="+", default=None)
    parser.add_argument("--allow-api", action="store_true", help="Explicitly permit paid agent API calls")
    parser.add_argument("--prepare-only", action="store_true", help="Generate and validate tasks without Docker or API")
    parser.add_argument("--usage-mode", choices=["off", "observed", "strict"])
    parser.add_argument("--initial-observation-steps", type=int)
    parser.add_argument("--input-token-limit", type=int)
    parser.add_argument("--output-token-limit", type=int)
    args = parser.parse_args()
    args.root = ROOT
    if args.case in {"pick-cube", "budget-input", "budget-output"} and args.usage_mode == "off":
        parser.error("Budget acceptance cases require observed (or a supported strict adapter)")
    api_cases = {"api", "sweep", "pick-cube", "budget-input", "budget-output"}
    if args.case in api_cases and not args.prepare_only and not args.allow_api:
        parser.error("API cases require --allow-api; an environment variable alone never enables model calls")
    if args.case in api_cases and not args.model:
        parser.error("Provide --model for API/sweep cases")
    if args.case == "isolation" and args.prepare_only:
        parser.error("isolation checks require Docker; prepare-only applies to rollout tasks")
    run_id = args.run_id or f"harbor_{args.case}_" + new_run_id()
    from harbor_runners.config import name
    name(run_id)
    report_dir = ROOT / "runs/test_results" / run_id
    report_dir.mkdir(parents=True, exist_ok=False)
    report = dict(case=args.case, run_id=run_id, image=args.image, status="running",
                  gpu_required=args.case != "isolation", api_requested=args.case in api_cases,
                  visual_reasoning_verified=False, source_files=source_identity())
    atomic_json(report_dir / "report.json", report)
    code = 1
    key = None
    try:
        if args.case in api_cases and not args.prepare_only:
            key = input_key(args, required=True)
        if args.case == "isolation":
            if args.image is None:
                args.image = load_config()["image"]
            command = ["docker", "run", "--rm", "--network", "none", "--pids-limit", "128",
                       "--security-opt", "no-new-privileges:true", args.image, "python", "-c", ISOLATION_CHECK]
            result = subprocess.run(command, capture_output=True, text=True, timeout=90)
            (report_dir / "isolation.stdout.txt").write_text(result.stdout)
            (report_dir / "isolation.stderr.txt").write_text(result.stderr)
            code = result.returncode
        else:
            filename = {"scripted": "smoke_scripted.yaml", "invalid": "smoke_scripted.yaml", "cancel": "smoke_scripted.yaml",
                        "api": "smoke_api.yaml", "sweep": "cast_coil_rollout.yaml",
                        "pick-cube-scripted": "cube_pick_place_rollout.yaml", "pick-cube": "cube_pick_place_rollout.yaml",
                        "budget-input": "cube_pick_place_rollout.yaml", "budget-output": "cube_pick_place_rollout.yaml"}[args.case]
            config = load_config(ROOT / "configs/harbor/experiments" / filename,
                                 overrides={"image": args.image, "model": args.model})
            if args.case == "sweep":
                from harbor_runners.config import expand
                expand(config, difficulties=["easy", "medium", "hard"])
            config.update(attempts=args.attempts, concurrency=args.concurrency,
                          timeout_sec=args.timeout_sec)
            report["image"] = config["image"]
            if args.gpu_devices is not None:
                config.update(gpu_devices=args.gpu_devices, gpus=len(args.gpu_devices))
            scripted_scenario = {"scripted": "normal", "invalid": "invalid", "cancel": "cancel",
                                 "pick-cube-scripted": "pick-cube"}.get(args.case)
            if scripted_scenario is not None:
                config["usage"] = {"mode": "off"}  # no model, not a budget acceptance claim
            if args.case in {"budget-input", "budget-output"}:
                config["usage"]["limits"] = dict(input_tokens=1 if args.case == "budget-input" else 3_000_000,
                                                 output_tokens=1024 if args.case == "budget-output" else 1_000_000)
                for instance in config["instances"]:
                    instance["instruction"] += (
                        " This is a budget-stop test. Continue making tool calls that inspect feedback and explain "
                        "the next action in detail until the model budget ends, even if the physical task succeeds.")
            apply_usage_args(config, args)
            for instance in config["instances"]:
                if args.initial_observation_steps is not None:
                    instance["initial_observation_steps"] = args.initial_observation_steps
                instance["simulator"]["seed"] = args.seed
                instance["name"] = instance["name"].rsplit("seed", 1)[0] + "seed" + str(args.seed)
            run = prepare(config, ROOT, run_id, scripted_scenario=scripted_scenario)
            report["run_dir"] = str(run)
            report["frozen_manifest_sha256"] = hashlib.sha256((run / "manifest.json").read_bytes()).hexdigest()
            for filename in ("usage_binding.resolved.json", "agent_urls.resolved.json", "usage_sources.resolved.json"):
                path = run / filename
                if path.exists():
                    report[filename] = json.loads(path.read_text())
            atomic_json(report_dir / "report.json", report)
            code = 0 if args.prepare_only else launch(run, ROOT, api_key=key, env_file=args.env_file)
            index_path = run / "rollout_index.json"
            if index_path.exists():
                report["rollout_index"] = str(index_path)
                report["result"] = json.loads(index_path.read_text())
                if args.case in {"pick-cube", "pick-cube-scripted"}:
                    trials = report["result"]["trials"]
                    matched = len(trials) == report["result"]["expected_trials"]
                    for trial in trials.values():
                        verdict = trial.get("verification", {})
                        matched &= (trial.get("pipeline_passed", False) and verdict.get("task_success") is True
                                    and verdict.get("reward") == 1)
                        if args.case == "pick-cube":
                            matched &= trial.get("budget_qualified") is True
                    report["expectation_met"] = bool(matched)
                    code = 0 if matched else 1
                if args.case in {"budget-input", "budget-output"}:
                    dimension = args.case.removeprefix("budget-") + "_tokens"
                    trials = report["result"]["trials"]
                    matched = len(trials) == report["result"]["expected_trials"]
                    for trial in trials.values():
                        usage = trial.get("usage") or {}
                        stop = usage.get("stop") or {}
                        matched &= (trial.get("status") == "complete" and
                            trial.get("verification", {}).get("reward") == 0 and
                            stop.get("reason") in {"budget_exceeded", "budget_exhausted"} and
                            dimension in stop.get("dimensions", []) and
                            trial.get("stop_timings", {}).get("agent_stopped_at") is not None and
                            trial.get("stop_timings", {}).get("worker_stopped_at") is not None)
                    report.update(expected_failure=args.case, expectation_met=bool(matched),
                        trial_outcome="failed" if matched else "see_rollout_index")
                    code = 0 if matched else 1
                if args.case in {"invalid", "cancel"}:
                    expected_reason = "invalid_action" if args.case == "invalid" else "cancelled"
                    trials = report["result"]["trials"]
                    matched = len(trials) == report["result"]["expected_trials"]
                    for trial in trials.values():
                        if trial.get("status") != "complete" or trial.get("harbor_exception") is not None:
                            matched = False
                            continue
                        record = json.loads((Path(trial["archive"]) / "segments/segment_2/result.json").read_text())
                        matched &= (record["reason"] == expected_reason and record["control_steps"] == 0
                                    and trial["verification"]["reward"] == 0)
                    report["expected_failure"] = expected_reason
                    report["expectation_met"] = bool(matched)
                    code = 0 if matched else 1
        report["status"] = "prepared_only" if args.prepare_only else "passed" if code == 0 else "failed"
    except Exception as error:
        # No exception repr/traceback in the shared report; native logs retain diagnostics.
        report.update(status="failed", error=type(error).__name__)
        print(redact(str(error), tuple(x for x in (key, args.api_key) if x)), file=sys.stderr)
    finally:
        atomic_json(report_dir / "report.json", report)
        print(f"Acceptance report: {report_dir / 'report.json'}")
    return code


if __name__ == "__main__":
    sys.exit(main())
