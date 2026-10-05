"""Select the complete, audited Buzz reference for the frozen Harbor tier."""
from types import SimpleNamespace
from topogym.planning.harbor_bridge.callbacks import prepare_output, data_path
from .runner import worker
from .reference_policy import run_reference_policy


def run_feedback_policy(session, output, *, variation, compiled=None, feedback_finish=False):
    if compiled is None and not feedback_finish:
        return run_reference_policy(session, output, variation=variation)
    # Explicit custom recipes retain the development runner. The default sweep
    # never falls back to its unqualified generic online planner.
    if feedback_finish and (compiled is None or variation != "easy"):
        raise ValueError("Custom feedback finish requires an easy compiled prefix")
    output = prepare_output(session, output, __file__)
    cfg = session.env.config
    args = SimpleNamespace(output=output, variant=variation, seed=cfg.seed, part="all", control_mode="JOINT_ABS",
        compute_backend=cfg.compute_backend, physics_dt=cfg.physics_dt_s, control_decimation=cfg.control_decimation,
        solver_substeps=cfg.solver_substeps, episode_seconds=1800., grasp_height=.012, grasp_tilt=75.,
        compiled_actions=data_path(compiled) if compiled else None, feedback_finish=feedback_finish, v12_performance=False)
    return worker(args, session=session)
