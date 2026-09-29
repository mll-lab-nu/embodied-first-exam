"""Three ring counts through the standard Env and shared Nyx recorder."""

import json
import os
from pathlib import Path
import traceback

import numpy as np
import pytest

from topogym.config import SimulatorConfig
from topogym.simulator.env import Env
from topogym.utils.io import to_jsonable, write_json_atomic
from orbits_stability_evidence import measure, summarize
from runtime_evidence import RuntimeEvidence

pytestmark = [pytest.mark.genesis, pytest.mark.fem, pytest.mark.ipc, pytest.mark.render]


@pytest.mark.parametrize('tier', ('easy', 'medium', 'hard'))
def test_passive_stability(tier):
    root = os.environ.get('TOPOGYM_ORBITS_OUTPUT')
    assert root, 'Use scripts/test_orbits_stability.py to preserve source and evidence'
    duration = float(os.environ.get('TOPOGYM_ORBITS_DURATION', '10'))
    window = float(os.environ.get('TOPOGYM_ORBITS_WINDOW', '2'))
    dt = float(os.environ.get('TOPOGYM_ORBITS_DT', '.0025'))
    seed = int(os.environ.get('TOPOGYM_ORBITS_SEED', '0'))
    steps = round(duration/(10*dt))
    assert steps >= 2 and abs(steps*10*dt-duration) < 1e-9
    assert abs(window/dt-round(window/dt)) < 1e-9
    folder = Path(root)/tier
    cfg = SimulatorConfig(task_id='orbits', variation_id=tier, enable_privileged=True,
                          physics_dt_s=dt, control_decimation=10,
                          max_physics_steps=steps*10+10, work_dir=folder/'episodes')
    evidence = RuntimeEvidence(folder, 'orbits', cfg)
    env = Env(cfg)
    error = None
    rows = []
    try:
        with evidence.stage('reset') as stage:
            observed, info = env.reset(seed=seed)
            stage['metadata'] = to_jsonable(env.episode_metadata)
            evidence.sample(env, observed, info, label='initial')
            assert info['physics_step'] == 0 and cfg.reset_physics_steps == 0
            task = env._task
            assert task.layout.ring_count == {'easy': 2, 'medium': 3, 'hard': 4}[tier]
            assert cfg.grasp_assist.model == 'none'
            volume_path, = (folder/'episodes').glob('*/assets/cord_volume.npz')
            with np.load(volume_path) as volume:
                rings = volume['surface_ring_indices'].copy()
                initial_centers = volume['spawn'][rings].mean(axis=1)
                lengths = np.linalg.norm(np.diff(initial_centers, axis=0), axis=1)
            state = env.privileged.get('world')
            context = dict(layout=task.layout, origin=task.origin, yaw_deg=task.config['yaw_deg'],
                           surface_rings=rings, initial_lengths=lengths,
                           handle_vertices=task.placement_vertices['handle'],
                           fixed_positions={name: state['bodies'][name]['position_m'].copy()
                                            for name in task.placement_remainder})

        with (folder/'stability_ticks.jsonl').open('x') as stream:
            def sample_tick(record):
                row = dict(physics_step=record['state']['physics_step'],
                           sim_time_s=record['state']['sim_time_s'],
                           **measure(record['world'], **context))
                rows.append(row)
                stream.write(json.dumps(row, allow_nan=False)+'\n')
                stream.flush()

            sample_tick(env.tick_record())
            unsubscribe = env.add_state_sink(sample_tick)
            try:
                with evidence.stage('passive_gravity_hold'):
                    for _ in range(steps):
                        observed, _, done, truncated, info = env.step({})
                        evidence.sample(env, observed, info, action={})
                        assert not done and not truncated, info
            finally:
                unsubscribe()
        result = summarize(rows, duration, window, dt_s=dt)
        result['seed'] = seed
        result['sample_interval_s'] = dt
        result['initial_to_final_handle_displacement_m'] = float(np.linalg.norm(
            np.array(rows[-1]['handle_position_m'])-rows[0]['handle_position_m']))
        evidence.report['stability'] = result
        write_json_atomic(folder/'stability.json', result)
        evidence.save()
        assert result['passed'], result
    except BaseException:
        error = traceback.format_exc()
        if rows and 'stability' not in evidence.report:
            result = summarize(rows, duration, window, dt_s=dt)
            evidence.report['stability'] = result
            write_json_atomic(folder/'stability.json', result)
        raise
    finally:
        try:
            evidence.close(error)
        finally:
            env.close()
