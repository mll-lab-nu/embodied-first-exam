"""Original reindex pickup/solve orchestration through the bound Session."""
from topogym.planning.harbor_bridge.callbacks import prepare_output
from .runner import worker


def run_feedback_policy(session, output, *, variation):
    output = prepare_output(session, output, __file__)
    cfg = session.env.config
    return worker(output, setting="current", part="solve", grasp_roll_deg=-45., grasp_style="side",
        physics_dt=cfg.physics_dt_s, solver_substeps=cfg.solver_substeps, control_decimation=cfg.control_decimation,
        no_rgb=not cfg.enable_rgb, compute_backend=cfg.compute_backend, variation=variation, route_mode="reindex",
        precision=cfg.precision, endpoint_depth=4.10 if variation == "hard" else 4.08, session=session)
