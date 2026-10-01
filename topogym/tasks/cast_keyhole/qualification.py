"""Historical placement evidence, exposed as owner metadata only.

Matches never enable or disable Task success, or certify a new physical run.
Old runs retain their original results and qualification records.
"""
import numpy as np


PLACEMENT_QUALIFICATIONS = {
    "cast_keyhole_easy": dict(
        geometry_sha256="90ca0ec73617ea5f1e108c9a1bdc6e86416b4464bbff6a490240c0dd6cfd0844",
        goal_region_identity="b5cf1e4d04572c15d99fdafb86fb0be50111ab01719276045c03555eb3810de2",
        evidence="runs/test_results/cast_keyhole_policy_20260928/trial_36_easy_goal_clearance/independent_goal_audit.json",
        audit_sha256="0300df3d363b07fdbec524459bc65d5a9a4681626be17d4f15306536887cfc2b",
        physical_evidence_sha256="aed9acc80754cf221b1027e4297a5b679e79a543d83a7dbd3b8055f240d1895c",
        raw_goal_stable_time_s=5.125000000000005,
        first_raw_goal_tick=19546,
        maximum_task_contact_penetration_m=.0004069171825032868,
        profile="default task parameters, seed 0, ALOHA EE_ABS, CPU, 25 ms World tick / 40 substeps, bilateral-contact contact_weld_v1",
    ),
    "cast_keyhole_hard": dict(
        geometry_sha256="f7d0ec58cdbf3870dbb698f7a7d4f039d3e59756b27304c1f5d561efa756ee14",
        goal_region_identity="c2e0046670ef2eacac75bd3719309253fa815c4a60c6f2849f7a9762fb68d13a",
        evidence="runs/test_results/cast_keyhole_policy_20260928/trial_33_hard_packed/independent_goal_audit.json",
        audit_sha256="af3f5c47400524eed43e4aae0692736fe5d897f5f485aa4cb23c9bed8b1dce95",
        physical_evidence_sha256="0aeebb719776a7320d358ad843e49d78cc205d9581ed687d107e8ee8e8e33357",
        raw_goal_stable_time_s=2.774999999999994,
        first_raw_goal_tick=21491,
        maximum_task_contact_penetration_m=.0004287678382704256,
        profile="default task parameters, seed 0, ALOHA EE_ABS, CPU, 25 ms World tick / 40 substeps, bilateral-contact contact_weld_v1",
    ),
    "cast_keyhole_medium": dict(
        geometry_sha256="b9a3e81f5cd907b0b6a3660bbd03768e7c54ecd2c8ba108f3e693c3b7a2c0697",
        goal_region_identity="32c4ffaef5eb8e023b017b87406d27ee83e783fa6bb9fc24696bdde1ab409345",
        evidence="runs/test_results/cast_keyhole_policy_20260928/trial_27_medium_pid/independent_goal_audit.json",
        audit_sha256="a2e0a99b4f741c52d4c7c058c76ec669599fc5d6f4118f43a788d2c485f795e0",
        physical_evidence_sha256="9a7004943932a817c5f69361858c8479697c85c7146a03cb4a59204497eedfbc",
        raw_goal_stable_time_s=2.9749999999999934,
        first_raw_goal_tick=18368,
        maximum_task_contact_penetration_m=.0003646257401330533,
        profile="default task parameters, seed 0, ALOHA EE_ABS, CPU, 25 ms World tick / 40 substeps, bilateral-contact contact_weld_v1",
    ),
}


def placement_qualification(task):
    record = PLACEMENT_QUALIFICATIONS.get(task.variation_id)
    if record is None or task.resource_hashes.get(task.geometry_resource) != record["geometry_sha256"]:
        return None
    if all(np.array_equal(task.config[key], value) for key, value in task.defaults.items()):
        if hasattr(task, "goal_region_identity") and task.goal_region_identity != record["goal_region_identity"]:
            return None
        return record
    # A seeded draw moves or re-finishes the same geometry. Only the listed axis
    # leaves may differ, within their envelope; the region is recomputed by the
    # same rule on the pinned side, so its hash is not compared.
    from topogym.tasks.scene_variation import within_envelope
    if not within_envelope(type(task), task.config):
        return None
    return {**record, "scope": "seeded scene variation within the declared envelope"}
