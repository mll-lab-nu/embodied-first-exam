#!/usr/bin/env python3
"""Freeze source/config/report before explicit real GPU benchmark validation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile


def http_smoke(instance,output,environment,source,log):
    """Exercise the actual single-owner server and sidecar finalization locally."""
    import signal
    import socket
    from topogym.benchmark.client import Robot
    with socket.socket() as port_probe:
        port_probe.bind(("127.0.0.1",0))
        port=port_probe.getsockname()[1]
    command=[sys.executable,"-m","topogym.benchmark","serve",str(instance),str(output),"--host","127.0.0.1","--port",str(port)]
    process=subprocess.Popen(command,cwd=source,env=environment,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    try:
        robot=Robot(base=f"http://127.0.0.1:{port}",timeout=900)
        start=robot.status()
        observation=robot.get_obs(depth="frames",video="both")
        assert observation.depth and robot.status()["control_steps"]==start["control_steps"]
        measured=dict(zip(robot.spec()["proprio_layout"],observation.meta["proprio"]["now"]))
        action=[]
        grippers=robot.spec()["robot_spec"]["grippers"]
        for name in robot.spec()["action_types"]["joint_position"]["layout"]:
            if name in measured:
                action.append(measured[name])
            else:
                group=name.split("/",1)[0]
                action.append(measured[grippers[group]["joints"][0]])
        result=robot.submit("joint_position",[action],video="both",depth="frames")
        assert result.meta["control_steps_chunk"]==1
        watched=robot.get_obs(seconds=1/robot.spec()["control_hz"],video="frames")
        assert watched.meta["control_steps_watch"]==1
        (output/"finish").touch()
        process.wait(timeout=7500)
        if process.returncode:
            raise RuntimeError(f"Supervisor exited {process.returncode}")
        final=json.loads((output/"final.json").read_text())
        if final.get("grader_error"):
            raise RuntimeError(final)
        from topogym.benchmark.evidence import write_json
        write_json(output/"smoke.json",dict(protocol_passed=True,deterministic=final["deterministic"],replay_consistent=final["replay_consistent"],
            success=final["success"],http=True,finalized=final["finalized"],note="Actual HTTP + sidecar lifecycle; no Docker isolation claim"))
    finally:
        if process.poll() is None:
            os.killpg(process.pid,signal.SIGTERM)
            try:
                process.wait(timeout=10)
            finally:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))


def main():
    from topogym.benchmark.catalog import instances
    from topogym.benchmark.export import runtime_bundle
    from topogym.benchmark.evidence import digest, write_json
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--task",default="cube_pick_place")
    p.add_argument("--steps",type=int,default=2)
    p.add_argument("--http",action="store_true",help="Also exercise the real HTTP service and supervisor")
    args = p.parse_args()
    if not 1 <= args.steps <= 400:
        p.error("Use 1..400 control steps for this infrastructure smoke test")
    output = args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    manifest = runtime_bundle(PROJECT,output/"source.tar.gz")
    write_json(output/"source-manifest.json",manifest)
    instance = instances(task=args.task)[0][0]
    instance.update(mode="limited",source_sha256=digest(manifest))
    write_json(output/"instance.json",instance)
    report = dict(status="running",scope="real CUDA/Nyx protocol and independent replay; no oracle claim",instance_sha256=digest(instance),source_sha256=digest(manifest))
    write_json(output/"report.json",report)
    with tarfile.open(output/"source.tar.gz") as archive:
        archive.extractall(output/"source",filter="data")
    # Explicit read-only robot asset source; record each consumed source byte.
    assets = PROJECT/"assets/robots"
    write_json(output/"robot-assets.json",{str(x.relative_to(assets)):hashlib.sha256(x.read_bytes()).hexdigest()
        for x in sorted(assets.rglob("*")) if x.is_file()})
    environment = dict(os.environ,PYTHONPATH=str(output/"source"),TOPOGYM_ASSET_ROOT=str(PROJECT/"assets"))
    command = [sys.executable,"-m","topogym.benchmark","smoke-child",str(output/"instance.json"),str(output/"evidence"),"--steps",str(args.steps)]
    try:
        with (output/"process.log").open("wb") as log:
            if args.http:
                http_smoke(output/"instance.json",output/"evidence",environment,output/"source",log)
            else:
                subprocess.run(command,cwd=output/"source",env=environment,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=10800)
        report.update(status="passed",results=json.loads((output/"evidence/smoke.json").read_text()))
        if not report["results"]["replay_consistent"]:
            report["status"] = "replay_mismatch"
    except Exception as error:
        report.update(status="failed",error=str(error))
        raise
    finally:
        write_json(output/"report.json",report)
        print(output/"report.json")


if __name__ == "__main__":
    main()
