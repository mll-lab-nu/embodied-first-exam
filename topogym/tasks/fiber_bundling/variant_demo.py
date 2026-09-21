"""Run, recheck and archive one explicit cable variant without reusing other scenes' proof."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

from .run_config import load_run_config

ROOT=Path(__file__).resolve().parents[3]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instance",type=Path)
    parser.add_argument("--attempt",default="hybrid_01")
    parser.add_argument("--stage",choices=("gate","physics","complete","render_archive"),default="complete")
    parser.add_argument("--press-radius",type=float)
    parser.add_argument("--entry-envelope",type=float)
    parser.add_argument("--max-presses",type=int,default=16)
    parser.add_argument("--mode",default="greedy_hybrid",choices=("greedy_hybrid","greedy_orbit","spiral","axial"))
    parser.add_argument("--run-id")
    parser.add_argument("--base-dt",type=float,choices=(.002,.001,.0005),default=.002)
    parser.add_argument("--stability-dir",default="stability")
    args=parser.parse_args()
    instance=args.instance.resolve()
    cfg=load_run_config(instance/"config.yaml")
    if not args.attempt.replace("_","").isalnum():
        parser.error("Use a simple attempt name")
    attempt=instance/args.attempt
    attempt.mkdir(exist_ok=True)
    radius=float(cfg.task.geometry.ring_inner_radius_m)
    press=args.press_radius if args.press_radius is not None else .0353+radius-.0135
    envelope=args.entry_envelope if args.entry_envelope is not None else min(.017,.016+radius-.0135)
    status=dict(instance=instance.name,attempt=args.attempt,stage=args.stage,status="running",commands=[])
    def save():
        status["updated_at_utc"]=datetime.now(timezone.utc).isoformat()
        (attempt/"workflow_status.json").write_text(json.dumps(status,indent=2)+"\n")
    save()
    env=dict(os.environ,OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",PYOPENGL_PLATFORM="egl")
    def run(module,arguments,log):
        command=[sys.executable,"-m",f"topogym.tasks.fiber_bundling.{module}",*map(str,arguments)]
        status["current_stage"]=module
        status["commands"].append(command)
        save()
        print(json.dumps(dict(stage=module,instance=instance.name,log=str(log))),flush=True)
        log.parent.mkdir(parents=True,exist_ok=True)
        with log.open("w") as output:
            result=subprocess.run(command,cwd=ROOT,env=env,stdout=output,stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f"{module} exited {result.returncode}; inspect {log}")
    try:
        gate=instance/args.stability_dir/"result.json"
        if args.stage == "render_archive":
            recorded_plan=json.loads((attempt/"baseline/plan.json").read_text())
            gate=Path(recorded_plan["stability_gate"])
            if not gate.is_absolute():
                gate=ROOT/gate
        status["stability_directory"]=str(gate.parent)
        if args.stage != "render_archive":
            for name,dt in (("baseline",args.base_dt),("half_step",args.base_dt/2)):
                folder=gate.parent/name
                if not (folder/"report.json").exists():
                    if folder.exists() and any(folder.iterdir()):
                        raise RuntimeError(f"Incomplete existing probe in {folder}; inspect before restarting")
                    run("anchored_probe",["--config",instance/"config.yaml","--output",folder,"--dt",dt,
                        "--settle-seconds",5,"--release-seconds",5,"--load-scale",.1,"--performance-mode"],
                        gate.parent/f"{name}.log")
                if not json.loads((folder/"report.json").read_text())["passed"]:
                    raise RuntimeError(f"Load probe failed: {folder}")
            if not gate.exists():
                run("assess_anchored",[gate.parent],gate.parent/"comparison.log")
            if not json.loads(gate.read_text())["stability_passed"]:
                raise RuntimeError("This variant has not passed its paired loading gate")
            if args.stage != "gate":
                for name,dt in (("baseline",args.base_dt),("half_step",args.base_dt/2)):
                    folder=attempt/name
                    if not (folder/"report.json").exists():
                        if folder.exists() and any(folder.iterdir()):
                            raise RuntimeError(f"Incomplete existing trial in {folder}; use a new attempt name")
                        trial_module="refined_variant_trial" if args.base_dt < .001 else "variant_trial"
                        run(trial_module,["--config",instance/"config.yaml","--stability",gate,
                            "--output",folder,"--dt",dt,"--mode",args.mode,"--grasp-link","trunk_04",
                            "--press-radius",press,"--entry-envelope",envelope,"--max-presses",args.max_presses],
                            attempt/f"{name}.log")
                    if not json.loads((folder/"report.json").read_text())["full_threading_verified"]:
                        raise RuntimeError(f"Full robot threading failed: {folder}")
        if args.stage != "gate":
            from .assess_ik import assess
            comparison=assess(attempt/"baseline",attempt/"half_step")
            (attempt/"timestep_validation.json").write_text(json.dumps(comparison,indent=2)+"\n")
            status["strict_timestep_convergence_passed"]=comparison["passed"]
            if not comparison["checks"]["both_complete_physical_runs_passed"]:
                raise RuntimeError("Both complete physical runs are required")
        if args.stage in ("complete","render_archive"):
            baseline=attempt/"baseline"
            from .render_ready import render_lock
            with render_lock(baseline):
                if not (baseline/"render_report.json").exists():
                    run("render_robot_sequence",[baseline,"--backend","cpu","--renderer","rasterizer","--clean"],
                        attempt/"render.log")
            run_id=args.run_id or f"2026-09-17_{instance.name.replace('.','p')}_{args.attempt}"
            metadata=ROOT/"runs/demo_metadata/fiber_bundling"/run_id
            if not (metadata/"archive_manifest.json").exists():
                run("archive_variant",[baseline,attempt/"half_step","--run-id",run_id],attempt/"archive.log")
            status["metadata_directory"]=str(metadata.relative_to(ROOT))
            status["status"]="archived_complete"
        else:
            status["status"]="gate_passed" if args.stage == "gate" else "both_full_runs_passed"
        save()
    except Exception as error:
        status.update(status="stopped",failure=str(error))
        save()
        raise


if __name__=="__main__":
    main()
