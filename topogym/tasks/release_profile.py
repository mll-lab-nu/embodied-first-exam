"""Public environment choices of the active release (merged-v19), shared by fixed and sampled task builders.

This module contains environment parameters only, never oracle routes. Scene
draws keep their seed and placement; explicit release leaves override defaults.
"""
from copy import deepcopy

PROFILE = "merged-v19"
IPC_FAMILIES = frozenset({"knot_untying", "rope_threading", "orbits", "slotted_post_ring"})


def merge(base, changes):
    result = deepcopy(base)
    for key, value in changes.items():
        result[key] = merge(result.get(key, {}), value) if isinstance(value, dict) else deepcopy(value)
    return result


def environment_inputs(family, tier, *, variation=None, seed=0, parameters=None):
    below_easy = tier in ("very_easy", "easier")
    if tier not in ("easy", "medium", "hard") and not (
            family in ("blanket_flatten", "rope_threading") and below_easy):
        raise ValueError(f"No {PROFILE} profile for tier {tier!r}")
    params, overrides, changes = deepcopy(parameters or {}), {}, []
    if family == "rope_threading":
        # One environment for all five tiers. The ring layout below belongs to the three original tiers' scenes; the
        # below-easy scenes (one cradle or ring) keep their own geometry.
        scene = {}
        if not below_easy:
            geometry = dict(ring_yaw_deg=dict(R2=53.13010235415598), ring_offsets_m=dict(R2=[-.035, -.05, 0.]))
            if tier != "easy":
                geometry["ring_offsets_m"]["R3"] = [0., .06, 0.]
                geometry["ring_mount_sides"] = dict(R3=-1)
            scene = dict(geometry=geometry)
        params = merge(params, dict(**scene, rope_mesh=dict(spacing=.0055, sides=12),
            rope_material=dict(E=5e6), rope_reference_shape="initial", rope_robot_contact="fingers",
            aperture_contact_allowance_m=.001, aperture_check_profile="round_ring",
            terminal=dict(maximum_speed_m_s=.01)))
        overrides = dict(physics_dt_s=.04, control_decimation=1, solver_substeps=1, reset_physics_steps=0,
            ipc_options=dict(newton_tolerance=.003, linear_system_tolerance=.00003,
                             collision_detection_method="linear_bvh"),
            grasp_assist=dict(model="ipc_soft_band_v1", max_translation_error_m=.025, max_penetration_m=.006,
                targets=[dict(entity="rope", max_strain_ratio=2., strength=1000., require_exposed_patch=False)]))
        changes.append("contact_relaxed_v16: explicit material/contact/grasp/timing/terminal candidate, the scene's own "
                       "ring layout" if below_easy else
                       "contact_relaxed_v16: explicit geometry/material/contact/grasp/timing/terminal candidate")
    elif family == "blanket_flatten":
        # v16 live goal (the user's decision, 2026-10-03): the task default 0.90 accepted a folded corner. The graders'
        # replay hold accepts 0.92 (harbor_templates/topogym/common/rcb_topogym.py REPLAY_TOLERANCES). The packaged v14
        # cloth states are re-keyed for it, not prepared again (scripts/topogym_merge_candidate.py).
        params = merge(params, dict(minimum_coverage_ratio=.95))
        overrides["grasp_assist"] = dict(model="pbd_local_patch_v1", stable_time_s=.03,
            targets=[dict(entity="blanket", spatial_radius_m=.018, material_radius_m=.018,
                          max_strain_ratio=1.3 if tier in ("very_easy", "easier", "easy") else 1.5)])
        changes.append("public birth UV support and explicit two-hand patch assistance; live coverage 0.95")
    elif family == "horseshoe_ring":
        changes.append("local default ring-clearance geometry and matching recommended grasp")
    elif family == "hedgehog_in_cage" and tier == "hard":
        changes.append("local fixed_v3_s5_post geometry and elevated initial pose")
    elif family == "fiber_bundling":
        from topogym.config.registry import task_definition
        task = task_definition(family, variation or tier, seed)(params, seed=seed)
        layout = task.layout_class(**{**task.config["geometry"], "seed": task.seed})
        overrides["grasp_assist"] = dict(model="contact_weld_v1", targets=[dict(entity="fiber_bundle",
            link=f"trunk_{layout.trunk_segments - 2:02d}",
            center_m=[layout.trunk_length_m / layout.trunk_segments / 2., 0., 0.], radius_m=.025)])
        changes.append("explicit local sheath grasp; original three-tier defaults remain unassisted")
    return params, overrides, changes
