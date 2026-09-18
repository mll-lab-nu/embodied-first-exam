"""Exact-variant entry point with 2/1/0.5 ms integration, using the same physical policy."""
import argparse
from pathlib import Path

if __name__ == "__main__":
    from .snapshot_trial import maybe_run_snapshot
    maybe_run_snapshot("variant_trial", __file__)

from .ik_search import BundleIKTrial


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,required=True)
    parser.add_argument("--stability",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--dt",type=float,choices=(.002,.001,.0005),default=.002)
    parser.add_argument("--mode",choices=("greedy_hybrid","greedy_orbit","spiral","axial"),default="greedy_hybrid")
    parser.add_argument("--press-radius",type=float,default=.0353)
    parser.add_argument("--entry-envelope",type=float,default=.016)
    parser.add_argument("--max-presses",type=int,default=16)
    parser.add_argument("--grasp-link",choices=("trunk_03","trunk_04","trunk_05"),default="trunk_04")
    args=parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("Use a fresh output directory")
    if not .025 <= args.press_radius <= .06 or not .010 <= args.entry_envelope <= .017 or args.max_presses < 1:
        parser.error("Invalid forming parameters")
    args.backend,args.performance_mode,args.stage="cpu",True,"full"
    args.grip_x,args.regrasp_back,args.motion_scale=.015,False,1.
    args.rear_link,args.rear_x,args.park_clearance,args.feed_depth="trunk_04",.015,.110,.034
    args.selection,args.order,args.preparation_passes="orbit",None,1
    args.grasp_angle,args.assist=150.,True
    args.cycles,args.orbit_radius,args.tilt=1,.022,18.
    args.entry_start,args.entry_end,args.roll_span,args.feed_speed=.070,.025,70.,.012
    trial=BundleIKTrial(args)
    (args.output/"source/variant_trial.py").write_bytes(Path(__file__).read_bytes())
    (args.output/"source/snapshot_trial.py").write_bytes(Path(__file__).with_name("snapshot_trial.py").read_bytes())
    if not trial.run()["passed"]:
        raise SystemExit(1)


if __name__=="__main__":
    main()
