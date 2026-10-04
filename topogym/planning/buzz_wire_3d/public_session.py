"""Existing Buzz controller and optional compiled reference in a bound Session."""
from types import SimpleNamespace
from topogym.planning.harbor_bridge.callbacks import prepare_output, data_path
from .runner import worker


def run_feedback_policy(session, output, *, variation, compiled=None, feedback_finish=False):
    output = prepare_output(session, output, __file__)
    cfg = session.env.config
    args = SimpleNamespace(output=output, variant=variation, seed=cfg.seed, part="all", control_mode="JOINT_ABS",
        compute_backend=cfg.compute_backend, physics_dt=cfg.physics_dt_s, control_decimation=cfg.control_decimation,
        solver_substeps=cfg.solver_substeps, episode_seconds=1800., grasp_height=.012, grasp_tilt=75.,
        compiled_actions=data_path(compiled) if compiled else None, feedback_finish=feedback_finish, v12_performance=False)
    return worker(args, session=session)
