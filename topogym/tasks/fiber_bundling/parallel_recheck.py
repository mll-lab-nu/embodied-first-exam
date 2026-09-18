"""Independently recheck a recorded controller while its baseline is still running.

The controller starts from reset and loads frozen baseline sources. Existing
partial runs are observed, never restarted or overwritten.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[3]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instance",type=Path)
    parser.add_argument("--attempt",default="hybrid_01")
    args=parser.parse_args()
    instance=args.instance.resolve();attempt=instance/args.attempt
    baseline=attempt/"baseline";half=attempt/"half_step"
    while not (baseline/"source/variant_trial.py").exists():
        workflow=attempt/"workflow_status.json"
        if workflow.exists() and json.loads(workflow.read_text()).get("status")=="stopped":
            raise RuntimeError("Baseline workflow stopped before its controller snapshot was ready")
        time.sleep(5)
    plan=json.loads((baseline/"plan.json").read_text())
    policy=plan["policy_parameters"]
    command=[sys.executable,"-m","topogym.tasks.fiber_bundling.variant_trial",
        "--config",str(baseline/"config.yaml"),"--stability",plan["stability_gate"],
        "--output",str(half),"--dt",str(plan["dt"]/2),"--mode",policy["mode"],
        "--grasp-link",plan["grasp_link"],"--press-radius",str(plan["press_radius_m"]),
        "--entry-envelope",str(policy["entry_envelope_m"]),"--max-presses",str(policy["max_presses"])]
    record=dict(scope="independent full physics run in parallel; frozen baseline controller; no state restoration",
        command=command,started_at_utc=datetime.now(timezone.utc).isoformat(),status="running")
    attempt.mkdir(exist_ok=True)
    record_path=attempt/"parallel_recheck.json"
    record_path.write_text(json.dumps(record,indent=2)+"\n")
    if not half.exists():
        env=dict(os.environ,OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",PYOPENGL_PLATFORM="egl")
        with (attempt/"half_step_parallel.log").open("w") as log:
            result=subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        record["returncode"]=result.returncode
        if result.returncode:
            record.update(status="stopped",failure="Half-step process failed; inspect half_step_parallel.log and report.json")
            record_path.write_text(json.dumps(record,indent=2)+"\n")
            raise RuntimeError(record["failure"])
    for folder in (baseline,half):
        while not (folder/"report.json").exists():
            if folder==half and record.get("returncode",0):
                record.update(status="stopped",failure="Half-step process exited without a final report")
                record_path.write_text(json.dumps(record,indent=2)+"\n")
                raise RuntimeError(record["failure"])
            time.sleep(5)
        if not json.loads((folder/"report.json").read_text())["full_threading_verified"]:
            record.update(status="stopped",failure=f"Physical run did not complete: {folder}")
            record_path.write_text(json.dumps(record,indent=2)+"\n")
            raise RuntimeError(record["failure"])
    # A sequential supervisor may stop when it sees this independently running
    # half-step directory. Preserve that operational record before archiving.
    workflow=attempt/"workflow_status.json"
    while workflow.exists():
        status=json.loads(workflow.read_text())
        if status.get("status")=="archived_complete":
            record.update(status="archived_complete")
            record_path.write_text(json.dumps(record,indent=2)+"\n")
            return
        if status.get("status")=="running" and status.get("current_stage") in ("render_robot_sequence","archive_variant"):
            time.sleep(5)
            continue
        break
    if workflow.exists():
        shutil.copy2(workflow,attempt/"workflow_before_parallel_archive.json")
    record.update(status="both_full_runs_passed")
    record_path.write_text(json.dumps(record,indent=2)+"\n")
    shutil.copy2(record_path,baseline/"parallel_recheck.json")
    result=subprocess.run([sys.executable,"-m","topogym.tasks.fiber_bundling.variant_demo",str(instance),
        "--attempt",args.attempt,"--stage","render_archive"],cwd=ROOT)
    record["status"]="archived_complete" if result.returncode==0 else "archive_stopped"
    record_path.write_text(json.dumps(record,indent=2)+"\n")
    if result.returncode:
        raise SystemExit(result.returncode)


if __name__=="__main__":
    main()
