"""Finite-instance placement qualification; historical results stay unchanged."""
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
    record = MEDIUM_QUALIFICATION
    if (task.variation_id != "hedgehog_in_cage_medium" or task.model_revision != record["model_revision"]
            or task.seed != record["seed"] or to_jsonable(task.config) != to_jsonable(task.defaults)
            or task.resource_hashes.get(task.asset_resource) != record["asset_resource_sha256"]
            or _generator_hash() != record["generator_sha256"]):
        return None
    if hasattr(task, "goal_region_identity") and task.goal_region_identity != record["goal_region_identity"]:
        return None
    return record
