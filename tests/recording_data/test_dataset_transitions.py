"""真实命令、历史分支与数据读回；只编写，未运行。

HDF5 用 hdf5 marker 明确选择，需要安装 h5py；不以 importorskip 把缺失依赖
冒充支持。其余案例只写小型 JSONL，不构造模拟器。
"""
from dataclasses import replace
import json

import numpy as np
import pytest

from topogym.data import EpisodeDatasetWriter
from topogym.simulator.history import Transition
from topogym.utils.snapshots import freeze


def transition(*, state_id=2, previous_state_id=0, control_step=1,
               physics_step=2, branch_id=0, before=0.0, after=0.25, info=None):
    return Transition(
        episode_id="episode-A", branch_id=branch_id,
        previous_state_id=previous_state_id, state_id=state_id,
        control_step=control_step, physics_step=physics_step,
        sim_time_s=physics_step * 0.01, physics_steps=2, action_duration_s=0.02,
        observation=freeze({"robot": {"left": {"joint_position_rad": np.full(6, before),
                                                "finger_position_m": np.full(2, 0.015)}}}),
        action=freeze({"left": {"joint_position_rad": np.array([1., -.4, .5, .1, -.2, .3]),
                                "gripper_position_m": 0.002}}),
        next_observation=freeze({"robot": {"left": {"joint_position_rad": np.full(6, after),
                                                     "finger_position_m": np.full(2, 0.015)}}}),
        reward=0.0, terminated=False, truncated=False, info=freeze(info or {}),
    )


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_closed_dataset_keeps_audit_rows_but_invalidates_abandoned_future(tmp_path):
    path = tmp_path / "closed.jsonl"
    with EpisodeDatasetWriter(path) as writer:
        writer.append(transition())
        writer.finish({})
    writer.on_lifecycle({"kind": "rewind", "episode_id": "episode-A", "invalidated_state_ids": [2]})
    manifest = json.loads(writer.manifest.read_text())
    assert manifest["dataset_status"] == "complete"
    assert manifest["path"] == path.name and path.exists()
    assert manifest["active_transition_indices"] == []
    assert manifest["invalidated_transition_indices"] == [0]


def test_rewind_event_invalidates_future_even_without_another_transition(tmp_path):
    path = tmp_path / "rewound.jsonl"
    with EpisodeDatasetWriter(path) as writer:
        writer.append(transition())
        writer.append(transition(state_id=4, previous_state_id=2, control_step=2, physics_step=4))
        writer.on_lifecycle(dict(kind="rewind", episode_id="episode-A", branch_id=1,
                                state_id=2, invalidated_state_ids=[3, 4]))
        writer.finish({})
    manifest = json.loads(writer.manifest.read_text())
    assert manifest["active_transition_indices"] == [0]
    assert manifest["invalidated_transition_indices"] == [1]
    assert len(read_rows(path)) == 2  # retained only as audit evidence


def test_new_branch_can_start_at_original_anchor_without_duplicate_checkpoint(tmp_path):
    with EpisodeDatasetWriter(tmp_path / "original_anchor.jsonl") as writer:
        writer.append(transition())
        writer.append(transition(state_id=4, previous_state_id=2, control_step=2, physics_step=4))
        writer.append(transition(state_id=6, previous_state_id=2, control_step=2,
                                 physics_step=4, branch_id=1, info={"branch_parent_state_id": 2}))
        writer.finish({})
    manifest = json.loads(writer.manifest.read_text())
    assert manifest["active_transition_indices"] == [0, 2]


def test_jsonl_preserves_command_even_when_motion_does_not_reach_target(tmp_path):
    """受阻后的测量不等于指令；不能再把下一帧观测伪装成 action。"""
    path = tmp_path / "episode.jsonl"
    with EpisodeDatasetWriter(path) as writer:
        writer.append(transition())
        writer.finish({"task_success": False, "termination_reason": "caller_stopped"})
    row, = read_rows(path)
    assert row["action"]["left"]["joint_position_rad"] == [1., -.4, .5, .1, -.2, .3]
    assert row["next_observation"]["robot"]["left"]["joint_position_rad"] == [0.25] * 6
    assert row["action"]["left"]["gripper_position_m"] == 0.002
    assert row["next_observation"]["robot"]["left"]["finger_position_m"] == [0.015] * 2
    assert row["physics_steps"] == 2
    assert row["action_duration_s"] == pytest.approx(0.02)
    manifest = json.loads(writer.manifest.read_text())
    assert manifest["dataset_status"] == "complete"
    assert manifest["result"]["task_success"] is False


def test_restored_branch_joins_to_original_state_without_overwriting_future(tmp_path):
    """旧未来保留，恢复关系显式写入 info；新 branch 可以回退物理时间。"""
    path = tmp_path / "branched.jsonl"
    records = [
        transition(),
        transition(state_id=4, previous_state_id=2, control_step=2, physics_step=4,
                   before=0.25, after=0.5),
        transition(state_id=6, previous_state_id=4, control_step=3, physics_step=6,
                   before=0.5, after=0.75),
        # Env allocates state 7 as the new branch root copied from historical
        # state 2. Its next completed action produces state 9.
        transition(state_id=9, previous_state_id=7, control_step=2, physics_step=4,
                   branch_id=1, before=0.25, after=0.4,
                   info={"branch_parent_state_id": 2}),
    ]
    with EpisodeDatasetWriter(path) as writer:
        for record in records:
            writer.append(record)
        writer.finish({})
    rows = read_rows(path)
    by_state = {row["state_id"]: row for row in rows}
    assert list(by_state) == [2, 4, 6, 9]
    branch = rows[-1]
    assert branch["previous_state_id"] == 7
    assert branch["branch_id"] == 1
    assert branch["sim_time_s"] < rows[-2]["sim_time_s"]
    source = by_state[branch["info"]["branch_parent_state_id"]]
    assert branch["observation"]["robot"]["left"]["joint_position_rad"] == source["next_observation"]["robot"]["left"]["joint_position_rad"]
    assert by_state[6]["next_observation"]["robot"]["left"]["joint_position_rad"] == [0.75] * 6


def test_discontinuous_state_link_leaves_incomplete_artifact(tmp_path):
    path = tmp_path / "invalid.jsonl"
    with pytest.raises(ValueError, match="discontinuous"):
        with EpisodeDatasetWriter(path) as writer:
            writer.append(transition())
            writer.append(transition(state_id=4, previous_state_id=1,
                                     control_step=2, physics_step=4))
    assert not path.exists()
    assert writer.temporary.exists()
    assert json.loads(writer.manifest.read_text())["dataset_status"] == "incomplete"


def test_fresh_episode_requires_new_dataset(tmp_path):
    with EpisodeDatasetWriter(tmp_path / "one.jsonl") as writer:
        writer.append(transition())
        with pytest.raises(ValueError, match="one episode"):
            writer.append(replace(transition(), episode_id="episode-B"))
    assert json.loads(writer.manifest.read_text())["dataset_status"] == "incomplete"


def test_clean_context_without_finish_does_not_publish(tmp_path):
    path = tmp_path / "unfinished.jsonl"
    with EpisodeDatasetWriter(path) as writer:
        writer.append(transition())
    assert not path.exists()
    assert writer.temporary.exists()
    assert json.loads(writer.manifest.read_text())["dataset_status"] == "incomplete"


@pytest.mark.parametrize("parent", [None, -1, True, "2", 4])
def test_restored_branch_requires_valid_parent_identity(tmp_path, parent):
    with EpisodeDatasetWriter(tmp_path / "invalid_parent.jsonl") as writer:
        writer.append(transition())
        with pytest.raises(ValueError, match="branch_parent_state_id"):
            writer.append(transition(state_id=5, previous_state_id=3, branch_id=1,
                                     info={"branch_parent_state_id": parent}))
    assert json.loads(writer.manifest.read_text())["dataset_status"] == "incomplete"


def test_branch_can_reference_history_state_without_control_transition(tmp_path):
    """任意物理 tick 可作恢复点；其父 ID 不必已在控制级 dataset 中出现。"""
    path = tmp_path / "physical_tick_parent.jsonl"
    with EpisodeDatasetWriter(path) as writer:
        writer.append(transition())
        writer.append(transition(state_id=5, previous_state_id=3, branch_id=1,
                                 info={"branch_parent_state_id": 1}))
        writer.finish({})
    rows = read_rows(path)
    assert 1 not in {row["state_id"] for row in rows}
    assert rows[-1]["info"]["branch_parent_state_id"] == 1


def test_restoration_parent_cannot_change_inside_same_branch(tmp_path):
    with EpisodeDatasetWriter(tmp_path / "changed_parent.jsonl") as writer:
        writer.append(transition(state_id=5, previous_state_id=3, branch_id=1,
                                 info={"branch_parent_state_id": 1}))
        with pytest.raises(ValueError, match="restoration parent cannot change"):
            writer.append(transition(state_id=7, previous_state_id=5, branch_id=1,
                                     control_step=2, physics_step=4,
                                     info={"branch_parent_state_id": 2}))


@pytest.mark.hdf5
def test_hdf5_readback_preserves_arrays_action_and_branch_fields(tmp_path):
    """显式选择本项时必须具备 h5py；缺依赖应失败，不能悄悄 skip。"""
    import h5py

    path = tmp_path / "episode.h5"
    first = transition()
    restored = transition(state_id=5, previous_state_id=3, control_step=2,
                          physics_step=4, branch_id=1, before=0.25, after=0.4,
                          info={"branch_parent_state_id": 2})
    with EpisodeDatasetWriter(path, metadata={"task_id": "fixture"}) as writer:
        writer.append(first)
        writer.append(restored)
        writer.finish({"task_success": False})
    with h5py.File(path, "r") as handle:
        assert handle.attrs["schema_version"] == "2.0.0"
        assert handle.attrs["dataset_status"] == "complete"
        source = handle["transitions/00000000"]
        branch = handle["transitions/00000001"]
        np.testing.assert_array_equal(source["action/left/joint_position_rad"][:], [1., -.4, .5, .1, -.2, .3])
        np.testing.assert_array_equal(source["next_observation/robot/left/joint_position_rad"][:], [0.25] * 6)
        assert source["action/left/gripper_position_m"][()] == pytest.approx(.002)
        np.testing.assert_array_equal(source["next_observation/robot/left/finger_position_m"][:], [.015] * 2)
        assert branch["branch_id"][()] == 1
        assert branch["previous_state_id"][()] == 3
        assert branch["info/branch_parent_state_id"][()] == 2
        assert json.loads(handle.attrs["result_json"])["task_success"] is False
