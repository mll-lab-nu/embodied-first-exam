"""Reuse the existing Blanket route with Harbor-owned physics and recording.

oraclefix 11c: every recorded row keeps the standard service's joint-step limit (topogym/planning/standard_rate.py), so
the privileged trajectory is also the standard reference. On v17 blanket hard the first contact tick re-solved the right
wrist by 0.0439 rad (row 229) and the standard twin was refused ("clipped or rejected"); easy and medium never exceed
0.029 rad per step, so their rows and trajectories are unchanged (a row within the limit is one ordinary step)."""
from topogym.planning.standard_rate import rate_limited_runner
from .robot_oracle import run_route_oracle


def run_feedback_policy(session, output, *, variation="easy"):
    if session.task != "blanket_flatten" or session.n_steps or session._resets:
        raise ValueError("Blanket reference requires a fresh frozen Blanket Session")
    if session.env._task.variation_id not in {variation, "blanket_flatten_" + variation}:
        raise ValueError("Blanket route differs from the frozen variation")
    return run_route_oracle(session.env, rate_limited_runner(session, control_mode="JOINT_ABS"), output, variation=variation)
