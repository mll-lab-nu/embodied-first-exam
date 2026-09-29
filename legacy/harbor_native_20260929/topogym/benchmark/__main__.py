"""Task authoring and simulator utilities; jobs run with official `harbor run`."""
import argparse
import json
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command",required=True)
    p = sub.add_parser("export")
    p.add_argument("--project",type=Path,default=Path(__file__).resolve().parents[2])
    p.add_argument("--output",type=Path,default=Path("harbor_tasks"))
    p.add_argument("--task")
    p.add_argument("--instance-file",type=Path)
    p.add_argument("--mode",choices=("limited","unlimited","both"),default="both")
    p.add_argument("--all-variants",action="store_true")
    p.add_argument("--seed",type=int,action="append",dest="seeds")
    p.add_argument("--image",default="topogym-simulator:20260929")
    for name in ("serve","serve-child"):
        p = sub.add_parser(name)
        p.add_argument("instance")
        p.add_argument("output")
        p.add_argument("--host",default="0.0.0.0")
        p.add_argument("--port",type=int,default=8000)
        if name == "serve":
            p.add_argument("--stay",action="store_true")
    p = sub.add_parser("collect")
    p.add_argument("output")
    p.add_argument("--timeout",type=float,default=7500)
    p = sub.add_parser("replay")
    p.add_argument("instance")
    p.add_argument("trajectory")
    p.add_argument("output")
    p.add_argument("--no-video",action="store_true")
    p = sub.add_parser("verify")
    p.add_argument("instance")
    p.add_argument("trajectory")
    p.add_argument("evidence")
    p.add_argument("logs")
    p = sub.add_parser("grade")
    p.add_argument("instance")
    p.add_argument("evidence")
    p.add_argument("logs")
    p = sub.add_parser("smoke-child")
    p.add_argument("instance")
    p.add_argument("output")
    p.add_argument("--steps",type=int,default=2)
    args = vars(parser.parse_args())
    command = args.pop("command")
    if command == "export":
        from .export import export
        args["seeds"] = args["seeds"] or (0,)
        print(export(**args))
    elif command == "serve":
        from .supervisor import run
        run(**args)
    elif command == "serve-child":
        from .service import serve
        serve(**args)
    elif command == "collect":
        from .supervisor import collect
        collect(**args)
    elif command == "replay":
        from .replay import replay
        args["record"] = not args.pop("no_video")
        replay(**args)
    elif command == "grade":
        from .grading import grade
        print(grade(**args))
    elif command == "verify":
        from .replay import verify_twice
        from .grading import grade
        from .evidence import write_json
        evidence = Path(args["evidence"])
        try:
            evidence.mkdir(parents=True,exist_ok=False)
            shutil.copyfile(args["trajectory"],evidence/"trajectory.npz")
            verify_twice(args["instance"],evidence/"trajectory.npz",evidence)
        except Exception as error:
            write_json(evidence/"final.json",dict(finalized=True,success=False,grader_error=1,error=str(error)))
        print(grade(args["instance"],evidence,args["logs"]))
    elif command == "smoke-child":
        smoke(**args)


def smoke(instance,output,steps=2):
    import numpy as np
    from .session import Session
    from .evidence import write_json, fingerprint
    from .replay import verify_twice
    output = Path(output)
    with Session(instance,output=output/"live") as session:
        original = fingerprint(session.env)
        observation = session.get_obs(depth="frames",video="both")
        assert observation.depth and all(np.isfinite(d).all() and (d>0).any() for d in observation.depth.values())
        q = observation.group("joint_pos",now=True)
        first = session.kinematics(dict(op="fk",q=q.tolist()))
        from .robot import matrix
        for name,camera in session.spec["cameras"].items():
            mount=camera["mount"]
            if mount["type"] == "link":
                transform=matrix(first["poses"][mount["parent_link"]]) @ np.array(mount["link_T_cam_cv"])
                np.testing.assert_allclose(np.linalg.inv(transform)[:3],observation.extrinsic_cv[name][0],atol=1e-8)
        tool=session.robot.tcp_frames[0]
        solved=session.kinematics(dict(op="ik",targets={tool:first["poses"][tool]},seed=q.tolist()))
        assert solved["ok"], "Stationary inverse kinematics did not recover measured TCP"
        assert fingerprint(session.env) == original, "Observation/FK changed state"
        try:
            session.submit("joint_position",[[float("nan")]*session.robot.action_dim])
            raise AssertionError("Nonfinite action accepted")
        except ValueError:
            assert fingerprint(session.env) == original
        # Step away from home to verify kinematics is independent of live state.
        target = session.robot.targets()
        target[0] += .001
        session.submit("joint_position",np.repeat(target[None,:],steps,axis=0),video="both",depth="frames")
        assert first == session.kinematics(dict(op="fk",q=q.tolist()))
        session.save(output/"trajectory.npz")
        live = session.verdict()
        write_json(output/"live.json",live)
        write_json(output/"spec.private-test.json",session.spec)
    final = verify_twice(instance,output/"trajectory.npz",output,live=live)
    write_json(output/"smoke.json",dict(protocol_passed=True,deterministic=final["deterministic"],replay_consistent=final["replay_consistent"],
        success=final["success"],note="Hold/micro-motion infrastructure test; not an oracle success"))


if __name__ == "__main__":
    main()
