#!/usr/bin/env python3
"""One run of an oracle (closed loop) or a recorded trajectory (open loop) under emulated GPU numeric noise.

Diagnostics only: never a grade, never a qualified oracle. Two emulations of what changes on another GPU model:

- --action-noise-rad S: add N(0, S) rad to every arm joint target at every control step (grippers unchanged), in
  both modes: small differences injected at every step, reaching the rope through the robot;
- --tolerance-scale F: multiply the IPC Newton and linear-solver tolerances by F (iteration-count flips).

Not used: writing perturbed FEM positions back through FiniteElementStateAccessorFeature.copy_from. Even with zero
added noise that round trip moved the held rope by 0.38 mm / 9.5 mm/s within one step compared with no round trip
(the accessor reads back identical positions and velocities), so it is not a neutral injection.

Builds the Session from the release profile's environment inputs (the same birth state as the frozen instance; the
report records the birth state_sha to check this). Runs inside the task image (rcb_topogym on PYTHONPATH) or from
the repository. Supported: rope_threading very_easy / easier through the below-easy Session callback.
"""
import argparse
import json
from pathlib import Path
import sys
import time
import traceback

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
try:
    import rcb_topogym as tooling
except ImportError:
    sys.path[:0] = [str(ROOT), str(ROOT / 'harbor_templates/topogym/common')]
    import rcb_topogym as tooling

METRICS = ('draped', 'support_points', 'minimum_rim_clearance_m', 'crossing_sequence', 'thickness_clear',
           'ambiguous', 'bimanual_handoff_complete', 'quiet', 'maximum_speed_m_s', 'stable_time_s')


def build_session(task, tier, tolerance_scale, max_steps):
    from topogym.tasks.release_profile import environment_inputs
    parameters, overrides, _ = environment_inputs(task, tier, variation=f'{task}_{tier}')
    ipc = dict(overrides['ipc_options'])
    for key in ('newton_tolerance', 'linear_system_tolerance'):
        ipc[key] *= tolerance_scale
    overrides = dict(overrides, ipc_options=ipc)
    session = tooling.Session(task, variation_id=f'{task}_{tier}', seed=0, task_parameters=parameters,
                              simulator_overrides=overrides, gripper_space='native', strict=True,
                              max_steps=max_steps)
    return session, ipc


def install_action_noise(session, sigma, seed):
    """Wrap this Session's step: every submitted row gets N(0, sigma) rad on its arm joint targets."""
    rng = np.random.default_rng(seed)
    grippers = set(session.robot.grip_index.values())
    joints = np.array([i for i in range(session.action_dim) if i not in grippers])
    counter = dict(steps=0, max_abs_rad=0.)
    step = session.step

    def noisy(action, **kwargs):
        row = np.asarray(action, dtype=np.float64).reshape(-1).copy()
        noise = rng.normal(0., sigma, size=len(joints))
        row[joints] += noise
        counter['steps'] += 1
        counter['max_abs_rad'] = max(counter['max_abs_rad'], float(np.abs(noise).max()))
        return step(row, **kwargs)
    session.step = noisy
    return counter


def divergence(actions, reference):
    n = min(len(actions), len(reference))
    diff = np.abs(np.asarray(actions[:n], float) - np.asarray(reference[:n], float)).max(axis=1)
    first = {f'{t:g}': (int(np.argmax(diff > t)) if (diff > t).any() else None) for t in (0., 1e-6, 1e-4, 1e-2)}
    return dict(rows=len(actions), reference_rows=len(reference), first_row_above_rad=first,
                max_abs_rad=float(diff.max()) if n else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task', default='rope_threading', choices=('rope_threading',))
    parser.add_argument('--tier', required=True, choices=('very_easy', 'easier'))
    parser.add_argument('--mode', required=True, choices=('closed', 'open'))
    parser.add_argument('--reference', type=Path, required=True, help='trajectory.npz of the graded privileged run')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--action-noise-rad', type=float, default=0.)
    parser.add_argument('--noise-seed', type=int, default=0)
    parser.add_argument('--tolerance-scale', type=float, default=1.)
    parser.add_argument('--hold-steps', type=int, default=50, help='open loop: repeat the last row this many times')
    parser.add_argument('--max-steps', type=int, default=6000)
    parser.add_argument('--solution', type=Path, help="packaged solution dir whose topogym/planning holds the oracle "
                        "(as the Harbor bridge attaches it); default: the importable topogym.planning")
    args = parser.parse_args()
    if args.solution is not None:
        import topogym
        topogym.__path__.insert(0, str(args.solution.resolve() / 'topogym'))
    if args.action_noise_rad < 0 or args.tolerance_scale <= 0:
        parser.error('noise must be >= 0 and the tolerance scale > 0')
    args.output.mkdir(parents=True, exist_ok=False)
    reference = np.load(args.reference)['actions']
    report = dict(format='oracle_noise_sensitivity_v1', started=time.time(), qualification='diagnostic only',
                  **{k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()})
    session = counter = None
    try:
        session, ipc = build_session(args.task, args.tier, args.tolerance_scale, args.max_steps)
        report.update(ipc_options=ipc, birth_state_sha=session.state_sha())
        if args.action_noise_rad > 0:
            counter = install_action_noise(session, args.action_noise_rad, args.noise_seed)
        session.record_start()
        if args.mode == 'closed':
            from topogym.planning.harbor_bridge.below_easy import run_feedback_policy
            result = run_feedback_policy(session, args.output, variation=args.tier)
            report['policy_result'] = {k: result.get(k) for k in ('reason', 'control_steps', 'task_success')}
        else:
            success_row = None
            for i, row in enumerate(reference):
                done = session.step(row)
                if success_row is None and session.success():
                    success_row = i + 1
                if done:
                    break
            held = 0
            while not session.success() and held < args.hold_steps and session.episode_end is None:
                session.step(reference[-1])
                held += 1
            report.update(success_row=success_row, hold_steps_used=held)
        report['status'] = 'done'
    except BaseException as error:
        report.update(status='failed', error=f'{type(error).__name__}: {error}', traceback=traceback.format_exc())
    finally:
        if session is not None:
            env = session.env
            metrics = getattr(env._task.result, 'metrics', {}) or {}
            report.update(success=bool(session.success()), n_steps=int(session.n_steps),
                          sim_time_s=float(session.sim_time_s), final_state_sha=session.state_sha(),
                          episode_end=session.episode_end, metrics={k: metrics.get(k) for k in METRICS})
            if counter is not None:
                report['noise'] = counter
            if session._recording is not None:
                actions = session.record_stop()
                np.save(args.output / 'actions.npy', actions)
                if args.mode == 'closed':
                    report['divergence'] = divergence(actions, reference)
            session.close()
        report['wall_s'] = time.time() - report['started']
        (args.output / 'report.json').write_text(json.dumps(report, indent=2, default=str) + '\n')
    print(json.dumps({k: report.get(k) for k in ('status', 'success', 'n_steps', 'success_row', 'error')}))


if __name__ == '__main__':
    main()
