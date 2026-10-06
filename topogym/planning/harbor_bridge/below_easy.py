"""Existing below-easy controllers in a Harbor-owned, frozen Session.

Only robot actions are submitted. Native Harbor replay determines the grade;
local historical success never qualifies this source/configuration.
"""
from .actions import SessionPolicyRunner
from .callbacks import prepare_output, run_stages


def run_feedback_policy(session, output, *, variation):
    family = session.task
    if family not in ("cast_coil", "cast_keyhole", "lock_picking", "buzz_wire_3d",
                       "fiber_bundling", "interlocked_claws", "rope_threading", "knot_untying",
                       "blanket_flatten") or variation not in ("very_easy", "easier"):
        raise ValueError("Expected a supported below-easy oracle")
    if session.n_steps or session._resets:
        raise ValueError("Below-easy oracle requires a fresh frozen Session")
    if session.env._task.variation_id not in (variation, family + "_" + variation):
        raise ValueError("Reference tier differs from frozen task")
    if family == "rope_threading":
        from topogym.utils.io import to_jsonable
        assist = to_jsonable(session.env.config.grasp_assist)
        if (not isinstance(assist, dict) or assist.get("model") != "ipc_soft_band_v1"
                or not any(target.get("entity") == "rope" for target in assist.get("targets", []))):
            raise ValueError("Rope oracle requires declared ipc_soft_band_v1 assistance targeting rope; "
                             "rebuild a matching instance before execution")
    output = prepare_output(session, output, __file__)
    cfg = session.env.config
    if family == "blanket_flatten":
        from topogym.planning.blanket_flatten.public_session import run_feedback_policy as run
        return run(session, output, variation=variation)
    if family == "knot_untying":
        from topogym.planning.knot_untying.public_session import run_feedback_policy as run
        return run(session, output, variation=variation)
    if family == "cast_coil":
        from topogym.planning.cast_coil.public_session import run_feedback_policy as run
        return run(session, output)
    if family == "cast_keyhole":
        from topogym.planning.cast_keyhole.public_session import run_feedback_policy as run
        return run(session, output)
    if family == "lock_picking":
        from topogym.planning.lock_picking.runner import worker
        return worker(output, setting="current", part="solve", grasp_roll_deg=-45., grasp_style="side",
            physics_dt=cfg.physics_dt_s, solver_substeps=cfg.solver_substeps,
            control_decimation=cfg.control_decimation, no_rgb=not cfg.enable_rgb,
            compute_backend=cfg.compute_backend, variation=variation, route_mode="simplified",
            precision=cfg.precision, endpoint_depth=3.08, session=session)
    if family == "fiber_bundling":
        import json
        from .callbacks import data_path
        from topogym.planning.fiber_bundling.stages import stages
        selection = json.loads(data_path(f"fiber_bundling/{variation}/selection.json").read_text())
        return run_stages(session, output, stages, selection=selection)
    if family == "rope_threading":
        from topogym.planning.rope_threading.policy import ThreadingPolicy
        return SessionPolicyRunner(session).run_policy(request_id="below-easy-threading",
            policy=ThreadingPolicy(session.env, part="solve", speed_scale=1.),
            submission_hash=session.instance_sha, state_fields=("world",))
    if family == "interlocked_claws":
        from topogym.planning.interlocked_claws.simplified_policy import SimplifiedClawsPolicy
        from topogym.planning.interlocked_claws.simplified_preflight import prepare
        from topogym.utils.io import write_json_atomic
        runner = SessionPolicyRunner(session, control_mode="EE_ABS")
        acquired = runner.run_policy(request_id="below-easy-claws-acquire",
            policy=SimplifiedClawsPolicy(part="acquire"), submission_hash=session.instance_sha,
            state_fields=("world",))
        if acquired["reason"] != "policy_done":
            raise RuntimeError("Claws acquisition failed: " + acquired["reason"])
        motions, initial, offsets, audit = prepare(session.env, variation)
        write_json_atomic(output / "preflight.json", audit)
        if not audit["passed"]:
            raise RuntimeError("Claws robot preflight failed; see preflight.json")
        return runner.run_policy(request_id="below-easy-claws-solve",
            policy=SimplifiedClawsPolicy(motions=motions, initial=initial, offsets=offsets),
            submission_hash=session.instance_sha, state_fields=("world",))
    if family == "buzz_wire_3d":
        from topogym.planning.buzz_wire_3d.simplified_policy import SimplifiedBuzzOracle, make_stage_policy
        oracle = SimplifiedBuzzOracle(session.env, output, variant=variation, regrasp=True,
                                     finish_mode="low_slide_regrasp", terminal_contact_close=False)
        runner = SessionPolicyRunner(session)
        for name, parameters in oracle.stages(start="home", part="solve"):
            result = runner.run_policy(request_id=name, policy=make_stage_policy(session.env, parameters),
                                      submission_hash=session.instance_sha, state_fields=("world",))
            if session.success():
                return result
            if result["reason"] != "policy_done":
                raise RuntimeError(f"Buzz stage {name} failed: {result['reason']}")
        raise RuntimeError("Buzz oracle ended without native Task success")
