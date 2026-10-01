"""Finite-instance historical evidence; metadata only, never a success gate."""
from functools import lru_cache
import hashlib
from pathlib import Path

from topogym.utils.io import to_jsonable


MEDIUM_QUALIFICATION = dict(
    model_revision="waisted4_dark_wood_v1",
    seed=0,
    asset_resource_sha256="04ec99cd496aa997a866f1bd34456f8fc3cefc1d33456a281b2ae77117b43286",
    generator_sha256="f6d2af5709410a3924a6d91f2e6805272a037266153469b5b1738b64fa4f3187",
    goal_region_identity="d14126825ebb6016d3ae1667a66738e63b2d20b2ef76d53cffb277351144d42e",
    evidence="runs/hedgehog_oracle_20260930/diagnostic_audit_02/execution_audit.json",
    audit_sha256="e6dcb2a987f4adf85c5bf64930589a83b22d980b7ae6a4e2f2342ab5546f8ca7",
    physical_evidence_sha256="bfd252b074572422f439d36da3d1db9df954533ba3ac38d8bea402a3b2c16fbc",
    raw_goal_stable_time_s=2.7499999999999942,
    first_raw_goal_tick=2180,
    scope="medium default parameters, seed 0 only; no scene-variation qualification",
    profile="Panda/Robotiq JOINT_ABS, CPU float64, 25 ms World tick / 40 substeps, bilateral-contact contact_weld_v1",
    limitations="Assisted grasp, tick-end evidence; no friction-only, continuous-time or RGB qualification",
)


@lru_cache(maxsize=1)
def _generator_hash():
    path = Path(__file__).resolve().parents[2]/"assets/geometry/hedgehog_ellipse.py"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def placement_qualification(task):
    if task.variation_id == "hedgehog_in_cage_easy":
        return _easy_placement_qualification(task)
    record = MEDIUM_QUALIFICATION
    if (task.variation_id != "hedgehog_in_cage_medium" or task.model_revision != record["model_revision"]
            or task.seed != record["seed"] or to_jsonable(task.config) != to_jsonable(task.defaults)
            or task.resource_hashes.get(task.asset_resource) != record["asset_resource_sha256"]
            or _generator_hash() != record["generator_sha256"]):
        return None
    if hasattr(task, "goal_region_identity") and task.goal_region_identity != record["goal_region_identity"]:
        return None
    return record


EASY_QUALIFICATION = {'model_revision': 'simulator_v1',
 'seed': 0,
 'parameters': {'scale': 3.0,
                'center_xy_m': [-0.1356786, 0.05],
                'yaw_deg': 0.0,
                'mount_height_m': 0.04,
                'mount_width_m': 0.25,
                'stable_duration_s': 2.0,
                'minimum_separation_m': 0.01,
                'wood_tint': 1.0,
                'finish': 'wood',
                'scene_preset_id': 'lab_tasks_v1'},
 'input_sha256': {'assets/geometry/hedgehog_in_cage.py': 'dc3ee95e2e0b1b04b8cd3f15dbbb899ba3eab09059b1d5320a61c3f1170aa522',
                  'tasks/hedgehog_in_cage/common.py': '55af75f7be516f4ae3ca3b9bc7a58414b13c56e1693dff3adcd1e98e9077480f',
                  'tasks/hedgehog_in_cage/hedgehog_in_cage_easy.py': 'c3d18e9278db5c07365087d90999f6afceee6e7faa6a17c0c433e58cd6ae048d',
                  'hedgehog_in_cage/template.json': '9ba9a58c8541ccbcdf442a944cef26f1a58701c3fa5ed08fa9182bb22fd941a9'},
 'goal_region_identity': '1b53514dbc02e48081be9a67e6c9cf2f0fd6c3fe08a931608582f7737d18d909',
 'evidence': 'runs/hedgehog_three_20260930/easy_two_grasp_audit_01/execution_audit.json',
 'audit_sha256': '7c3dd2052b0152920248d033558aff0136f51b0831fef9245e589f25e7b1b148',
 'physical_evidence_sha256': 'b79b9564e7c81bcdd28c009eeee235aafb9bf2dfdbc11845047e1aafd518d7f7',
 'raw_goal_stable_time_s': 2.7249999999999943,
 'first_raw_goal_tick': 9475,
 'scope': 'easy default parameters, seed 0 only; no scene-variation qualification',
 'profile': 'Panda/Robotiq JOINT_ABS, CPU float64, 25 ms World tick / 40 substeps, two fresh '
            'bilateral-contact contact_weld_v1 acquisitions',
 'grasp_region': {'construction': 'Sphere enclosing the 30 mm contact neighborhoods for all '
                                  'declared stages',
                  'stage_contact_points_m': [[0.0, -0.07188010851409932, -0.04150000000001576],
                                             [0.0, 0.0, -0.063]],
                  'center_m': [0.0, -0.03594005425704966, -0.05225000000000788],
                  'radius_m': 0.06751333096379877,
                  'acquisition': 'Fresh closing intent and bilateral native contacts for each '
                                 'binding'},
 'limitations': 'Assisted grasp, tick-end evidence; no friction-only, continuous-time or RGB '
                'qualification'}


@lru_cache(maxsize=1)
def _easy_input_hashes():
    from topogym.assets.library import resource_path
    package = Path(__file__).resolve().parents[2]
    names = ("assets/geometry/hedgehog_in_cage.py",
             "tasks/hedgehog_in_cage/common.py",
             "tasks/hedgehog_in_cage/hedgehog_in_cage_easy.py")
    result = {name: hashlib.sha256((package/name).read_bytes()).hexdigest() for name in names}
    result["hedgehog_in_cage/template.json"] = hashlib.sha256(
        resource_path("hedgehog_in_cage/template.json").read_bytes()).hexdigest()
    return result


def _easy_placement_qualification(task):
    record = EASY_QUALIFICATION
    if (task.model_revision != record["model_revision"] or task.seed != record["seed"]
            or task.asset_resource is not None
            or to_jsonable(task.config) != record["parameters"]
            or to_jsonable(task.config) != to_jsonable(task.defaults)
            or _easy_input_hashes() != record["input_sha256"]):
        return None
    if hasattr(task, "goal_region_identity") and task.goal_region_identity != record["goal_region_identity"]:
        return None
    return record
