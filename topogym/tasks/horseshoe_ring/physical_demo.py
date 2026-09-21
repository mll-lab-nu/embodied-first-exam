"""Continuous gravity/contact execution of the replanned ALOHA horseshoe task."""
import argparse
import json
from pathlib import Path

import numpy as np

from .gravity_demo import array
from .physical_extraction import RelativeExtraction
from .physical_motion import PhysicalMotion
from .physical_place import release_ring
from .physical_plan import body_frame, combine_horseshoes, grasp_ring, horizontal_support


def extract_ring(motion, *, plan_only=False):
    planner = RelativeExtraction(motion.cfg.robot_control, motion.task.assembly.template,
        float(motion.cfg.task.scale), body_frame(motion), array(motion.robot.get_qpos()))
    current = np.array([0., 0., .001, 0., 0., 0.])
    q = array(motion.robot.get_qpos()).copy()
    plans, frames = [], []
    for index, goal in planner.guide():
        print(f"Planning ring extraction milestone {index}", flush=True)
        before = q.copy()
        for attempt, phase_offset in enumerate((0, 15, -15, 30, -30, 60, -60)):
            trial_goal = goal.copy()
            trial_goal[5] += np.deg2rad(phase_offset)*.05
            trial_q, trial_frames = before.copy(), []
            try:
                path, report = planner.plan_segment(current, trial_goal)
                for state in planner.samples(path):
                    trial_q, evidence = planner.solve(state, trial_q)
                    trial_frames.append(dict(guide_index=index, qpos=trial_q.tolist(), **evidence))
            except RuntimeError as exc:
                motion.events.append(dict(time_s=motion.step_count*motion.dt, phase="extraction_planning_retry",
                    guide_index=index, attempt=attempt, rejection=str(exc)))
                print(f"Replanning milestone {index}: {exc}", flush=True)
                if attempt == 6:
                    raise
                continue
            q = trial_q
            frames.extend(trial_frames)
            plans.append(dict(guide_index=index, attempt=attempt, **report))
            break
        current = path[-1]
        (motion.output / "planned_extraction.json").write_text(json.dumps(dict(
            complete=False, scope="IK plan; requires physical execution", plans=plans, frames=frames)))
    (motion.output / "planned_extraction.json").write_text(json.dumps(dict(
        complete=True, scope="IK plan; requires physical execution", plans=plans, frames=frames)))
    if plan_only:
        return frames
    phase = None
    for frame in frames:
        target = np.asarray(frame["qpos"])
        target[[6, 7, 14, 15]] = motion.q[[6, 7, 14, 15]]
        seconds = max(.05, np.ceil(np.max(np.abs(target-motion.q))/.3/.05)*.05)
        label = f"extract_ring_milestone_{frame['guide_index']}"
        motion.joint_segment(target, seconds, phase=label if phase != label else None)
        phase = label
    motion.hold(1., phase="confirm_ring_separation")
    # The table release planner also requires a geometrically separated start.
    # The ultimate verdict is made after gravity has settled the released ring.


def run(output, *, dt=.002, instance=None):
    motion = PhysicalMotion(output, dt=dt, instance=instance)
    try:
        motion.follow_old_fold()
        horizontal_support(motion)
        combine_horseshoes(motion)
        grasp_ring(motion)
        extract_ring(motion)
        release_ring(motion)
        remainder = (-motion.step_count) % round(.05/motion.dt)
        if remainder:
            motion.hold(remainder*motion.dt, phase="final_observation")
        if not motion.goal_state()["passed"]:
            raise RuntimeError("The released ring did not pass separation, table contact and settling checks")
        return motion.finish(success=True)
    except Exception as exc:
        motion.finish(failure=str(exc))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New evidence directory; existing results are preserved")
    parser.add_argument("--dt", type=float, default=.002)
    parser.add_argument("--instance", type=Path, help="Resolved seed instance from variant_generator")
    args = parser.parse_args()
    instance = json.loads(args.instance.read_text()) if args.instance else None
    result = run(args.output, dt=args.dt, instance=instance)
    print(json.dumps({key: result[key] for key in ("task_success", "simulated_seconds", "goal",
        "maximum_puzzle_penetration_m", "maximum_arm_tracking_error_rad")}, indent=2), flush=True)


if __name__ == "__main__":
    main()
