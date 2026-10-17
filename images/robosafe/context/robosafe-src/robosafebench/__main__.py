"""python -m robosafebench families | admit | run | verify | serve | show | tasks | score | audit | render | diagnose"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _static_clumsy(r: dict) -> str:
    """0.5.1: how many clumsy trajectories carried out struck the static scene (reported, not deciding admission)."""
    c = r.get("contact") or {}
    rows = [x for part in (c.values() if r.get("cameras") else [c]) for x in (part.get("static_clumsy") or [])]
    return f" static_clumsy={sum(1 for x in rows if x.get('static'))}/{len(rows)}" if rows else ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="robosafebench")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("families")
    p.add_argument("--ids", action="store_true")
    p = sub.add_parser("admit")
    p.add_argument("family", nargs="*")
    p.add_argument("--all", action="store_true")
    p.add_argument("--seeds", type=int, nargs="*")
    p.add_argument("--robot", default=None, help="admit on this robot (default: each family's first)")
    p.add_argument("--out", default="build/admit")
    p.add_argument("--interface", default="skill", choices=("skill", "pose", "control"), help="admit the scripted trajectories written for this interface")
    p.add_argument("--movers", default="scripted", choices=("scripted", "reactive"), help="0.5.1: the movers' condition (reactive: they answer the robot)")
    p.add_argument("--cameras", default=None, choices=("room", "onboard"), help="a room family: this camera condition only (default: both)")
    p.add_argument("--clock", default="paused", choices=("paused", "realtime"), help="0.5.1: realtime, the agent's time between calls passes in the world")
    p.add_argument("--think", type=float, default=None, help="realtime: synthetic think time before every call of a scripted strategy (s)")
    p.add_argument("--variant", default=None, help="admit this request wording with freshly executed same-family controls")
    p = sub.add_parser("run")
    p.add_argument("family"); p.add_argument("member"); p.add_argument("strategy")
    p.add_argument("--seed", type=int, default=0); p.add_argument("--robot", default=None); p.add_argument("--out", default=None)
    p.add_argument("--interface", default="skill", choices=("skill", "pose", "control"))
    p.add_argument("--cameras", default=None, choices=("room", "onboard"))
    p.add_argument("--evidence", default=None, help="hazard_hidden: the tier of hidden evidence (default: the family's first)")
    p.add_argument("--movers", default="scripted", choices=("scripted", "reactive"), help="0.5.1: the movers' condition (reactive: they answer the robot)")
    p.add_argument("--variant", default=None, help="run this member's declared request wording")
    p = sub.add_parser("verify")
    p.add_argument("record"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("serve")
    for a in ("--family", "--member"):
        p.add_argument(a, required=True)
    p.add_argument("--seed", type=int, default=0); p.add_argument("--robot", default="ur5e_2f85")
    p.add_argument("--host", default="127.0.0.1"); p.add_argument("--port", type=int, default=8765); p.add_argument("--out", default="out")
    p.add_argument("--condition", default="default")
    p.add_argument("--interface", default="skill", choices=("skill", "pose", "control"))
    p.add_argument("--variant", default=None)
    p.add_argument("--cameras", default=None, choices=("room", "onboard"), help="a room task: with the fixed camera, or with the robot's own cameras only")
    p.add_argument("--evidence", default=None, help="hazard_hidden: the tier of hidden evidence (default: the family's first)")
    p.add_argument("--movers", default="scripted", choices=("scripted", "reactive"), help="0.5.1: the movers' condition (reactive: they answer the robot)")
    p = sub.add_parser("show")
    p.add_argument("family"); p.add_argument("--out", default="build/show"); p.add_argument("--seed", type=int, default=0)
    p.add_argument("--strategy", default="reference"); p.add_argument("--robot", default=None)
    p.add_argument("--interface", default="skill", choices=("skill", "pose", "control"))
    p.add_argument("--cameras", default=None, choices=("room", "onboard"), help="a room family: the camera condition (default: its first, `room`)")
    p.add_argument("--evidence", default=None, help="hazard_hidden: the tier of hidden evidence (default: the family's first)")
    p = sub.add_parser("tasks")
    p.add_argument("--candidate-identity", type=Path, help="caller-pinned frozen-source/actual-image receipt JSON; required for current candidates of every profile")
    p.add_argument("--historical-native", action="store_true", help="explicit unstamped native history; makes no current-candidate admission claim")
    p.add_argument("--out", required=True); p.add_argument("--family", nargs="*"); p.add_argument("--seeds", type=int, nargs="*", default=[0])
    p.add_argument("--condition", default="default")
    p.add_argument("--variant", default=None, help="another wording of the request (rationale, named, exclusion): only the members that have it")
    p.add_argument("--interface", default="skill", choices=("skill", "pose", "control")); p.add_argument("--robot", default=None)
    p.add_argument("--cameras", default=None, choices=("room", "onboard"), help="room families under this camera condition (default: `room`)")
    p.add_argument("--with-sources", action="store_true", help="track F (long tasks): also the hazard_unnamed tasks of each embedded family's source (the dilution gap on one version)")
    p.add_argument("--evidence", default=None, help="hazard_hidden: this tier of hidden evidence only (default: every tier)")
    p.add_argument("--movers", default="scripted", choices=("scripted", "reactive"),
                   help="0.5.1 (B2): reactive, the families that declare reactive movers only, the condition in the key (scripted tasks are unchanged)")
    p = sub.add_parser("score", help="metrics from verdicts under a results directory")
    p.add_argument("dir", nargs="?"); p.add_argument("--run", default=None); p.add_argument("--json", action="store_true")
    p.add_argument("--rows", action="store_true", help="one line per trial instead of the tables")
    p.add_argument("--index", default=None, help="tasks/index.json when it is not next to the results")
    p.add_argument("--verdict", default=None, help="read verifier/verdict.<name>.json (a record judged again: scripts/rejudge.sh) where it exists")
    p.add_argument("--baselines", action="store_true", help="add the trivial strategies, run on every admitted family")
    p.add_argument("--boot", type=int, default=2000); p.add_argument("--seed", type=int, default=0)
    p = sub.add_parser("audit", help="admission add-ons: blind tests, visibility, what the agent image holds")
    p.add_argument("what", nargs="*", help="text | metadata | visibility | image (default: these four) | probe (runs one task through Harbor with a probe as the agent)")
    p.add_argument("--family", nargs="*"); p.add_argument("--out", default="build/audit")
    p.add_argument("--tasks", default=None, help="a directory of generated Harbor tasks (default: generated into the output directory)")
    p.add_argument("--seeds", type=int, nargs="*", default=None); p.add_argument("--json", action="store_true")
    p = sub.add_parser("render", help="replay a record into images and one JSON line per call")
    p.add_argument("record"); p.add_argument("--out", required=True); p.add_argument("--every-tick", type=int, default=0)
    p.add_argument("--mp4", action="store_true"); p.add_argument("--fps", type=float, default=None)
    p = sub.add_parser("diagnose", help="after the trials: named, the probe, a label per failed hazard trial, suspect twins")
    from robosafebench.diagnose import run as diagnose_run
    diagnose_run.add_arguments(p)
    args = ap.parse_args(argv)

    if args.cmd == "families":
        from robosafebench import families
        from robosafebench.families.base import track_label
        for fid, fam in families.registry().items():
            print(fid if args.ids else f"{fid:28s} {track_label(fam.track)} {fam.domain:9s} {fam.response:9s} {'/'.join(fam.members):24s} {fam.title}")
        return 0
    if args.cmd == "admit":
        from robosafebench import families, verify
        ids = sorted(families.registry()) if args.all or not args.family else args.family
        out_dir = Path(args.out)
        results, ok = {}, True
        for fid in ids:
            r = verify.admit(fid, out_dir, seeds=args.seeds, robot=args.robot, interface=args.interface, cameras=args.cameras,
                             movers=args.movers, clock=args.clock, think=args.think, variant=args.variant)
            results[fid] = r
            ok = ok and r["admitted"]
            both = (" cameras: " + " ".join(f"{c}={'y' if v else 'N'}" for c, v in r["cameras"].items())) if r.get("cameras") else (f" cameras: {args.cameras}" if args.cameras else "")
            print(f"{'ok  ' if r['admitted'] else 'FAIL'} {fid}: " + " ".join(f"{k}={'y' if r[k] else 'N'}" for k in ("reference", "nop", "nop_unattempted", "comply_harms", "negatives", "trivial", "replay", "contact_bump", "contact_reference", "static_reference", "static_strike", "body_reference", "damage_reference", "blind", "unseen_without_look", "attempt", "reference_end")) + both, flush=True)
        out_dir.mkdir(parents=True, exist_ok=True)
        name = "admit" + ("" if args.interface == "skill" else f"_{args.interface}") + ("" if args.movers == "scripted" else f"_{args.movers}") + ("" if args.clock == "paused" else f"_{args.clock}")
        if args.variant:
            import hashlib
            name += "_variant_" + hashlib.sha256(args.variant.encode()).hexdigest()[:12]
        (out_dir.parent / f"{name}.json").write_text(json.dumps(results, indent=1, default=str))
        return 0 if ok else 1
    if args.cmd == "run":
        from robosafebench import families, verify
        fam = families.get(args.family)
        key = {"family": args.family, "member": args.member, "seed": args.seed, "robot": args.robot or fam.robots[0]}
        if args.cameras:
            key["cameras"] = args.cameras
        if args.interface != "skill":
            key["interface"] = args.interface
        if args.evidence:
            key["evidence"] = args.evidence
        if args.movers != "scripted":
            key["movers"] = args.movers
        if args.variant:
            key["variant"] = args.variant
        rec = verify.run(key, args.strategy)
        ver = verify.verify(rec)
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(json.dumps(rec))
        print(json.dumps({k: ver.get(k) for k in ("pass", "outcome", "ended", "goal", "moments", "evidence_seen", "hidden", "marks", "events", "diagnostics", "replay", "error")}, indent=1, default=str))
        return 0
    if args.cmd == "verify":
        from robosafebench import verify
        ver = verify.verify(json.loads(Path(args.record).read_text()))
        print(json.dumps(ver, default=str) if args.json else json.dumps(ver, indent=1, default=str))
        return 0
    if args.cmd == "serve":
        from robosafebench.server import serve
        key = {"family": args.family, "member": args.member, "seed": args.seed, "robot": args.robot}
        if args.cameras:
            key["cameras"] = args.cameras
        if args.interface != "skill":
            key["interface"] = args.interface
        if args.variant:
            key["variant"] = args.variant
        if args.evidence:
            key["evidence"] = args.evidence
        if args.movers != "scripted":           # 0.5.1 (B2): the movers answer the robot
            from robosafebench import families
            if args.movers not in families.get(args.family).movers_conditions:
                ap.error(f"{args.family} is not served with --movers {args.movers} (Family.movers_conditions)")
            key["movers"] = args.movers
        serve(key, args.host, args.port, Path(args.out), args.condition)
        return 0
    if args.cmd == "show":
        import numpy as np
        from robosafebench import families, verify
        from robosafebench.sim.png import write_png
        fam = families.get(args.family)
        out = Path(args.out) / (args.family + (f"@{args.robot}" if args.robot else "") + (f"_{args.cameras}" if args.cameras else "") + ("" if args.interface == "skill" else f"_{args.interface}"))
        for member, level in [(m, lv) for m in fam.members for lv in (fam.evidence_levels(m) or (None,))]:
            if args.evidence and level and level != args.evidence:
                continue
            key = {"family": args.family, "member": member, "seed": args.seed, "robot": args.robot or fam.robots[0]}
            if args.cameras:
                key["cameras"] = args.cameras
            if args.interface != "skill":
                key["interface"] = args.interface
            if level:
                key["evidence"] = level
            rec = verify.run(key, args.strategy)
            f, inst, ep = verify.start(key)
            frames = [np.concatenate([ep.world.render(c) for c in ep.world.cameras], axis=1)]
            names = ["start"]
            for c in rec["calls"]:
                ep.execute({"tool": c["tool"], "args": {**c["args"], "images": False}})
                frames.append(np.concatenate([ep.world.render(cam) for cam in ep.world.cameras], axis=1))
                names.append(c["tool"])
            tag = f"{member}-{level}" if level else member
            for i, (name, frame) in enumerate(zip(names, frames)):
                write_png(out / f"{tag}_{i:02d}_{name}.png", frame)
            print(f"{tag}: request {fam.request(inst)!r}; {len(frames)} frames in {out}")
        return 0
    if args.cmd == "tasks":
        from robosafebench.harness import harbor
        candidate = json.loads(args.candidate_identity.read_text()) if args.candidate_identity else None
        for d in harbor.write_all(Path(args.out), family_ids=args.family, seeds=args.seeds, condition=args.condition,
                                  interface=args.interface, robot=args.robot, variant=args.variant, cameras=args.cameras,
                                  evidence=getattr(args, "evidence", None), with_sources=args.with_sources, movers=args.movers,
                                  candidate_identity=candidate, historical_native=args.historical_native):
            print(d)
        return 0
    if args.cmd == "score":
        from robosafebench import metrics
        if args.verdict:
            metrics.VERDICT_NAME = f"verdict.{args.verdict}.json"
        rows, note = [], {}
        if args.dir:
            rows += metrics.collect(Path(args.dir), Path(args.index) if args.index else None, args.run)
        if args.baselines:
            base, note = metrics.baseline_rows(log=lambda s: print(s, file=sys.stderr, flush=True))
            rows += base
        if not args.dir and not args.baselines:
            ap.error("score needs a results directory, --baselines, or both")
        if args.rows:
            print(json.dumps(rows) if args.json else metrics.render_rows(rows))
            return 0
        result = metrics.score(rows, n_boot=args.boot, seed=args.seed)
        if args.json:
            print(json.dumps({"runs": result, "baselines": note}))
        else:
            print(metrics.render(result) or "no trials with a verdict")
            if note.get("warning"):
                print("note: " + note["warning"])
            if note.get("not_admitted"):
                print("note: not admitted, left out of the baselines: " + ", ".join(note["not_admitted"]))
        return 0
    if args.cmd == "audit":
        from robosafebench.verify import audit
        return audit.main(args)
    if args.cmd == "diagnose":
        return diagnose_run.main(args)
    if args.cmd == "render":
        from robosafebench.verify import render
        info = render.render_record(json.loads(Path(args.record).read_text()), Path(args.out), every_tick=args.every_tick, mp4=args.mp4, fps=args.fps)
        print(json.dumps(info, indent=1))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
