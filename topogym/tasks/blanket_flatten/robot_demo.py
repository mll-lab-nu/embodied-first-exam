"""Run passive stability or complete robot execution and preserve physical states."""
from pathlib import Path
import shutil
import signal
import traceback

import hydra
from omegaconf import OmegaConf


@hydra.main(version_base='1.3', config_path='../../../configs', config_name='blanket_flatten_robot')
def main(cfg):
    import genesis as gs
    from topogym.utils.franka import initialize_franka_controller
    from .scene import BlanketSceneBuilder
    from .execution import Execution
    if cfg.run.mode not in ('stability', 'robot'):
        raise ValueError('mode must be stability or robot')
    output = Path(cfg.run.output).resolve()
    if (output/'config.yaml').exists():
        raise FileExistsError(f'Preserving existing run: {output}; choose a new run.output')
    output.mkdir(parents=True, exist_ok=True)
    OmegaConf.save(cfg, output/'config.yaml', resolve=True)
    snapshot = output/'source_snapshot'
    snapshot.mkdir(exist_ok=True)
    for path in Path(__file__).parent.glob('*.py'):
        shutil.copy2(path, snapshot/path.name)
    cfg.env.cameras = {}
    gs.init(backend=getattr(gs, str(cfg.env.genesis.backend)), precision=str(cfg.env.genesis.precision),
            seed=int(cfg.task.geometry.seed), logging_level='warning')
    task = BlanketSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(asset_dir=output/'assets')
    controller = initialize_franka_controller(scene=task.scene, manifest=task.tabletop.manifest,
                                              robot_cfg=cfg.robot_control, settle_steps=0)
    restoration = None
    if cfg.task.get('initial_state_recording'):
        from .initial_state import restore_selected_shape
        restoration = restore_selected_shape(task, cfg.task.initial_state_recording, output)
    execution = Execution(task, controller, cfg, output)
    execution.initial_state_restoration = restoration
    # Finish the current outer physics step before preserving an interrupted
    # attempt; an asynchronous exception inside the solver can leave a partial step.
    previous_interrupt = signal.signal(signal.SIGINT, lambda *_: setattr(execution, 'stop_requested', True))
    success, error, evidence = False, None, None
    try:
        if not restoration and cfg.task.variant in ('staged_corner_cross_twist_v3', 'staged_gathered_twist_v4'):
            from .preparation import prepare
            prepare(execution, cfg.task.preparation)
        execution.initialize()
        if cfg.run.mode == 'stability':
            success, evidence = execution.verify_passive_stability()
        else:
            if bool(cfg.task.execution.get('verify_stability_before_actions', False)):
                stable, _ = execution.verify_passive_stability()
                if not stable:
                    raise RuntimeError('Passive stability recheck failed before robot actions')
            execution.flatten()
            success, evidence = execution.final_check()
    except Exception as exc:
        error = str(exc)
        traceback.print_exc()
    except KeyboardInterrupt:
        error = 'Execution interrupted; incomplete physical attempt preserved'
        print(error, flush=True)
    finally:
        signal.signal(signal.SIGINT, previous_interrupt)
        report = execution.save(success=success, error=error, final_evidence=evidence)
        success = report['success']
        print(f"success={success} seconds={execution.time:.3f} report={output/'report.json'}", flush=True)
    if not success:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
