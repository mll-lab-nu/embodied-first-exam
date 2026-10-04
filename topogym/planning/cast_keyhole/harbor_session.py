"""Original three-tier Keyhole orchestration in an externally owned Session."""
from types import SimpleNamespace
from topogym.planning.harbor_bridge.callbacks import prepare_output
from .runner import worker


def run_feedback_policy(session, output, *, variation):
    output = prepare_output(session, output, __file__)
    cfg = session.env.config
    args = SimpleNamespace(variation=variation, seed=cfg.seed, part="all", backend=cfg.compute_backend,
        rgb=cfg.enable_rgb, tick=cfg.physics_dt_s, horizon=900., speed=1., gripper_close=.002)
    return worker(args, output, session=session)
