"""Strict success/failure of the six fixed-wrist essential families, for both hands.

Positive: the packaged oracle (task_library/<family>/solution/trajectory.npz) succeeds with the validated final hash,
and so does every packaged Wuji solution (task_library/<family>/solution/wuji/trajectory.npz).
Negative: no-op, truncated oracle, a dropped object (hand slowly opened mid-task: fail-fast), forged archive metadata,
wrong widths and ambiguous members all score 0; Wuji composes, is deterministic and its no-op fails.
The rotary-gait oracle (15,620 rows) runs only with DEXHAND_SLOW=1; scripts/dexhand/verify_oracles.py covers it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
SHARED = HERE / "shared"
sys.path.insert(0, str(SHARED))
import hands  # noqa: E402
from runtime import Session  # noqa: E402

FAMILIES = ["essential_cube_layer", "essential_held_joystick", "essential_pen_regrasp", "essential_two_object",
            "essential_rotary_gait", "essential_cube_reorient"]
# Final integration-state hashes of the validated Sharpa replays (artifacts/dexhand-visual-upgrade/validation-summary.json).
POSITIVE_SHA = {
    "essential_cube_layer": "081e0a9fd73fbc02b4990042f9b56498bdb5ea85b88492bef16cceeb7ad38d69",
    "essential_held_joystick": "b081e131313054171e9a902318a5cd501c70cbdbadadf1e9c608b984a6ef6cac",
    "essential_cube_reorient": "933fdad72ae9094acaf83024babb9219f1deeb5b4761c0df0c4b50726a0da181",
    "essential_pen_regrasp": "b78e45ad7b5c8f5e0205d27116df8538cf2d4d685c9dba33391376ea63ea99d4",
    "essential_rotary_gait": "0c984212d34406ea438c1a8ff0b95c7c532c086f32bac8609ffae85c6429603f",
    "essential_two_object": "64d049dbd9b7f3459a4dd7be1b404ea442b35e7bccdabf1ae4bdeabf371448eb",
}
# Final hashes of the packaged Wuji Hand 2.2 reference solutions (task_library/<family>/solution/wuji/; evidence:
# artifacts/ready-10-2026-10-14/wuji-success/<family>/, in-image grader and Harbor replays). Every family with a
# solution/wuji/ folder must be listed here.
WUJI_POSITIVE_SHA = {
    "essential_held_joystick": "7e93a37fa658bd1660d0c0e6a45e5753ab7040203584eaedc87198d781a18cd4",
    "essential_cube_reorient": "aa24c081855279160acafc4cb139ba8e537eaf971a3d8b7a215f2c3eb8ff36a8",
    "essential_rotary_gait": "584dc881a4a72a3efa869791a5d453a23285584527dba591f9e53d7bac851aef",
    "essential_cube_layer": "46a00e53b948765a6dec0def35d740916db0ef36fb583612b2a6a7a1020911df",
    "essential_two_object": "ac0f52b8307a02432dcfaf1629ae134c81e2d4e1fc7fc92ffe35433275cce714",
    "essential_pen_regrasp": "67ab8af449d82a8fc8f108a54c35d20f24d6baf1d1ecc1d16a623879566a07f2",
}
SLOW = os.environ.get("DEXHAND_SLOW") == "1"


def oracle(family: str) -> np.ndarray:
    sys.path.insert(0, str(SHARED / "solution"))
    from solution_parts import load

    return load(HERE / f"task_library/{family}/solution")[0]


def test_split_solution_is_bit_exact_and_below_two_megabytes():
    """rotary_gait's oracle is stored as parts (< 2 MB each) whose rows equal the validated archive's bit for bit."""
    import json

    directory = HERE / "task_library/essential_rotary_gait/solution"
    manifest = json.loads((directory / "trajectory.json").read_text())
    assert all((directory / part["file"]).stat().st_size < 2_000_000 for part in manifest["parts"])
    rows = oracle("essential_rotary_gait")
    assert rows.shape == (15620, 28) and rows.dtype == np.float64
    sys.path.insert(0, str(SHARED / "solution"))
    from solution_parts import rows_sha256

    assert rows_sha256(rows) == manifest["rows_sha256"]


def run(session: Session, rows) -> dict:
    session.reset()
    status = session.status()
    for row in rows:
        status = session.step(row)
        if status["done"]:
            break
    return status


def replay_cli(family: str, trajectory: Path, tmp_path: Path, *extra: str) -> dict:
    out = tmp_path / f"replay-{trajectory.stem}.json"
    subprocess.run([sys.executable, str(SHARED / "replay.py"), "--task", family, "--traj", str(trajectory),
                    "--out", str(out), *extra], check=True, cwd=SHARED, capture_output=True, timeout=600)
    return json.loads(out.read_text())


@pytest.mark.parametrize("family", FAMILIES)
def test_oracle_succeeds_with_validated_hash(family):
    if family == "essential_rotary_gait" and not SLOW:
        pytest.skip("15,620-row oracle; set DEXHAND_SLOW=1 (verify_oracles.py runs it)")
    status = run(Session(family), oracle(family))
    assert status["success"] and not status["failed"] and status["stage"] == status["total_stages"]
    assert status["state_sha"].startswith(POSITIVE_SHA[family])


def test_every_wuji_solution_has_a_validated_hash():
    packaged = {family for family in FAMILIES if (HERE / f"task_library/{family}/solution/wuji").is_dir()}
    assert packaged == set(WUJI_POSITIVE_SHA)


@pytest.mark.parametrize("family", sorted(WUJI_POSITIVE_SHA))
def test_wuji_solution_succeeds_in_two_fresh_replays(family, tmp_path):
    """solution/wuji/trajectory.npz: the packaged Wuji Hand 2.2 oracle (tools/ of the family folder made it)."""
    path = HERE / f"task_library/{family}/solution/wuji/trajectory.npz"
    first, second = replay_cli(family, path, tmp_path), replay_cli(family, path, tmp_path)
    assert first["success"] and second["success"] and first["hand"] == "wuji" and first["bad_trajectory"] == 0
    assert first["state_sha"] == second["state_sha"] == WUJI_POSITIVE_SHA[family]
    with np.load(path, allow_pickle=False) as archive:   # the wrist stays locked in every Wuji row
        rows = archive["actions"]
    assert first["steps"] == len(rows) and np.all(rows[:, :6] == Session(family, hand="wuji").hold_action()[:6])


@pytest.mark.parametrize("family", FAMILIES)
def test_nop_fails(family):
    session = Session(family)
    status = run(session, [session.hold_action()] * 300)
    assert not status["success"]


@pytest.mark.parametrize("family", [f for f in FAMILIES if f != "essential_rotary_gait"])
def test_truncated_oracle_fails(family):
    rows = oracle(family)
    status = run(Session(family), rows[: int(len(rows) * 0.8)])
    assert not status["success"]


@pytest.mark.parametrize("family", FAMILIES)
def test_dropped_object_fails_fast(family):
    """Follow the oracle, then open the hand over 2 s: the episode must fail within 1.2 s and stay failed."""
    session = Session(family)
    rows = oracle(family)
    prefix = min(len(rows) // 3, 400)
    status = run(session, rows[:prefix])
    assert not status["done"]
    opened = rows[prefix - 1].copy()
    opened[6:] = session.model.actuator_ctrlrange[6:, 0]
    for index in range(100):
        weight = (index + 1) / 100
        status = session.step((1 - weight) * rows[prefix - 1] + weight * opened)
        if status["done"]:
            break
    assert status["failed"] and not status["success"], status
    assert index < 60, f"failure came only after {index + 1} rows"
    assert status["reason"].startswith(("invariant:", "stage_guard:", "terminal_guard:"))
    steps = status["steps"]
    after = session.step(rows[prefix])  # later rows cannot recover a failed episode
    assert after["failed"] and after["steps"] == steps


def test_two_object_release_leaving_the_tray_fails():
    """Walnut A falling to the table or out of the tray footprint is an immediate invariant failure."""
    spec = Session("essential_two_object").spec
    assert spec["invariants"]["a_height"][0] == pytest.approx(0.135)
    assert spec["invariants"]["a_deposit_distance"][1] == pytest.approx(0.1)


@pytest.mark.parametrize("family", ["essential_cube_layer", "essential_two_object"])
def test_bad_archives_are_rejected_cleanly(family, tmp_path):
    rows = oracle(family)
    session = Session(family)
    cases = {
        "width27": dict(actions=rows[:, :27]),
        "wuji_label_sharpa_width": dict(actions=rows, hand=np.array("wuji")),
        "sharpa_label_wuji_width": dict(actions=rows[:, :26], hand=np.array("sharpa")),
        "unknown_hand": dict(actions=rows, hand=np.array("shadow")),
        "two_hands": dict(actions=rows, hand=np.array(["sharpa", "wuji"])),
        "empty_hand": dict(actions=rows, hand=np.array([], dtype="<U6")),
        "task_mismatch": dict(actions=rows, task=np.array("essential_rotary_gait")),
        "names_mismatch": dict(actions=rows, actuator_names=np.array(session.actuator_names[::-1])),
        "nan": dict(actions=np.where(np.arange(rows.size).reshape(rows.shape) == 7, np.nan, rows)),
        "empty": dict(actions=rows[:0]),
        "object_array": None,
    }
    for name, members in cases.items():
        path = tmp_path / f"{name}.npz"
        if members is None:
            np.savez(path, actions=np.array([[None] * 28], dtype=object))
        else:
            np.savez(path, **members)
        result = replay_cli(family, path, tmp_path)
        assert result["success"] is False and result["bad_trajectory"] == 1, name
    shadow = tmp_path / "shadow.npz"
    np.savez(shadow, actions=rows)
    with zipfile.ZipFile(shadow, "a") as archive:
        archive.writestr("actions", b"garbage")
    result = replay_cli(family, shadow, tmp_path)
    assert result["success"] is False and result["bad_trajectory"] == 1
    mismatch = tmp_path / "service.npz"
    np.savez(mismatch, actions=rows, hand=np.array("sharpa"))
    assert replay_cli(family, mismatch, tmp_path, "--trusted-service", "--hand", "wuji")["bad_trajectory"] == 1


def test_forged_success_members_are_ignored(tmp_path):
    session = Session("essential_cube_layer")
    path = tmp_path / "trajectory.npz"
    np.savez(path, actions=np.array([session.hold_action()] * 40), success=np.array(1), stage=np.array(3),
             reward=np.array(1.0))
    log = tmp_path / "log"
    env = {**os.environ, "RCB_TASK": "essential_cube_layer", "RCB_TRAJECTORY": str(path), "RCB_VERIFIER_LOG_DIR": str(log)}
    subprocess.run([sys.executable, str(SHARED / "grade.py")], env=env, cwd=SHARED, check=True, timeout=600)
    reward = json.loads((log / "reward.json").read_text())
    assert reward["success"] == 0 and reward["deterministic"] == 1 and reward["infra_error"] == 0
    assert all(isinstance(value, (int, float)) for value in reward.values())


WUJI_FAMILIES = list(FAMILIES)


def test_two_object_wuji_start_holds_both_walnuts():
    """The declared Wuji start (wuji_reset.json: finger targets + walnut start poses) holds both walnuts for 10 s."""
    import essential
    session = Session("essential_two_object", hand="wuji")
    declared = essential.wuji_initial_objects(session.frozen_spec)
    assert set(declared) == {"initial_position_a", "initial_quaternion_a", "initial_position_b", "initial_quaternion_b"}
    assert session.spec["parameters"]["initial_position_b"] == declared["initial_position_b"]
    assert session.frozen_spec["parameters"]["initial_position_b"] != declared["initial_position_b"]  # Sharpa unchanged
    features = session.features()
    assert features["b_finger_contacts"] >= 1 and features["a_hand_contacts"] >= 1 and features["b_support"] == 0
    status = run(session, [session.hold_action()] * 500)
    assert not status["failed"] and not status["success"] and status["steps"] == 500


def test_two_object_counts_wuji_fingers_by_link():
    import essential
    scene = essential.module(Session("essential_two_object").spec)
    assert scene._wuji_finger("r_wuji_r_ring_finger_middle") == "ring"
    assert scene._wuji_finger("r_wuji_r_pinky_middle") == "pinky"
    assert scene._wuji_finger("r_wuji_r_thumb_tip_sensor_frame") == "thumb"
    assert scene._wuji_finger("r_wuji_r_wrist") is None and scene._wuji_finger("right_index_DP") is None


def test_finger_of_takes_the_finger_named_first():
    """A later word names the phalanx: Wuji `r_ring_finger_middle` is the ring finger, `r_pinky_middle` the pinky."""
    assert hands.finger_of("r_ring_finger_middle") == "ring" and hands.finger_of("r_pinky_middle") == "pinky"
    assert hands.finger_of("r_middle_finger_middle") == "middle" and hands.finger_of("r_index_finger_middle") == "index"
    assert hands.finger_of("r_thumb_tip_sensor_frame") == "thumb" and hands.finger_of("right_pinky_DP") == "pinky"
    assert hands.finger_of("r_wrist") is None and hands.finger_of("") is None


def test_wuji_middle_phalanx_geoms_carry_their_own_finger():
    """The essential predicates count per-finger contacts by geom name; the Wuji ring and pinky middle phalanges must
    count for the ring and pinky (not the middle finger)."""
    model = Session("essential_cube_layer", hand="wuji").model
    names = {model.geom(g).name for g in range(model.ngeom)}
    assert "right_ring_wuji_r_ring_finger_middle_collision1" in names
    assert "right_pinky_wuji_r_pinky_middle_collision1" in names
    assert not any(name.startswith("right_middle_") and ("ring" in name or "pinky" in name) for name in names)


def test_wuji_reset_may_only_place_held_objects(tmp_path, monkeypatch):
    import essential
    spec = Session("essential_two_object").spec
    fake = tmp_path / "wuji_reset.json"
    fake.write_text(json.dumps({"family": "essential_two_object", "initial_fingers": {},
                                "initial_objects": {"deposit_position": [0, 0, 0]}}))
    monkeypatch.setattr(essential, "_HERE", tmp_path)
    with pytest.raises(ValueError, match="may not declare"):
        essential.wuji_initial_objects(spec)


@pytest.mark.parametrize("family", WUJI_FAMILIES)
def test_wuji_composes_deterministically_and_nop_fails(family, tmp_path):
    session = Session(family, hand="wuji")
    assert session.hand == "wuji" and session.action_dim == 26
    assert session.actuator_names[:6] == [f"wrist_{axis}_act" for axis in ("x", "y", "z", "rx", "ry", "rz")]
    assert session.actuator_names[6] == "r_wuji_r_THJ0" and session.actuator_names[-1] == "r_wuji_r_LFJ3"
    assert "r_wuji_r_index_finger_distal" in session.xml and "right_index_DP" not in session.xml
    hold = [session.hold_action()] * 300
    status = run(session, hold)
    assert not status["success"]
    path = tmp_path / "wuji.npz"
    session.save_trajectory(np.array(hold[:30]), path)
    first, second = replay_cli(family, path, tmp_path), replay_cli(family, path, tmp_path)
    assert first["hand"] == "wuji" and first["bad_trajectory"] == 0 and first["success"] is False
    assert first["state_sha"] == second["state_sha"]
    assert first["state_sha"] != Session(family).state_sha()


def test_hand_selection_from_environment(monkeypatch):
    monkeypatch.setenv("DEXHAND_HAND", "wuji")
    assert Session("essential_cube_layer").hand == "wuji"
    assert Session("essential_cube_layer", hand="sharpa").hand == "sharpa"
    monkeypatch.setenv("DEXHAND_HAND", "gripper")
    with pytest.raises(ValueError):
        Session("essential_cube_layer")
    monkeypatch.delenv("DEXHAND_HAND")
    assert Session("essential_cube_layer").hand == "sharpa"


def test_wuji_assets_are_the_pinned_manufacturer_files():
    manifest = hands.verify_wuji()
    assert manifest["upstream_model"] == "hand2/hand2_2"
    assert manifest["source_commit"] == "829c9aa27cb12c3a49d5b8d63c9869dd8f656702"


def test_wuji_is_mounted_like_the_wave_palm_up_with_the_thumb_on_the_same_side():
    """Flexing the Wuji index MCP lifts its tip toward the palm normal (+z, palm up), and the thumb sits on the
    Wave thumb's side of the hand (the hand_support rotation would mount the right Wuji palm-down)."""
    import mujoco

    wave = Session("essential_cube_layer")
    wuji = Session("essential_cube_layer", hand="wuji")
    palm = wuji.data.body("right_hand_C_MC")
    side = palm.xmat.reshape(3, 3)[:, 1]  # hand +Y: the Wave thumb side

    def tip(session, site):
        return session.data.site(site).xpos.copy()

    mujoco.mj_resetData(wuji.model, wuji.data)
    mujoco.mj_forward(wuji.model, wuji.data)
    straight = tip(wuji, "r_wuji_r_index_finger_tip")
    wuji.data.qpos[wuji.model.joint("r_wuji_r_index_finger_mcp_flex").qposadr[0]] = 1.0
    mujoco.mj_forward(wuji.model, wuji.data)
    assert tip(wuji, "r_wuji_r_index_finger_tip")[2] - straight[2] > 0.02
    thumb = tip(wuji, "r_wuji_r_thumb_tip") - palm.xpos
    pinky = tip(wuji, "r_wuji_r_pinky_tip") - palm.xpos
    assert thumb @ side > pinky @ side
    wave_thumb = wave.data.body("right_thumb_MC").xpos - wave.data.body("right_hand_C_MC").xpos
    assert wave_thumb @ side > 0


def test_wuji_model_keeps_no_unreferenced_wave_meshes():
    """Replaced Wave meshes are dropped, so the compiled Wuji model cannot depend on MuJoCo's process mesh cache."""
    import xml.etree.ElementTree as ET

    root = ET.fromstring(Session("essential_held_joystick", hand="wuji").xml)
    meshes = {mesh.get("name") for mesh in root.iter("mesh")}
    used = {geom.get("mesh") for geom in root.iter("geom") if geom.get("mesh")}
    assert meshes == used
    assert not any(name.startswith("right_") for name in meshes)
