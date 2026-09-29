from dataclasses import replace
import json
import numpy as np
import pytest
from topogym.benchmark.evidence import load_trajectory,write_json,digest
from topogym.benchmark.grading import grade


def test_normalization_only_discards_float64_last_bits():
    from topogym.benchmark.evidence import rounded_state
    assert rounded_state({"x":1.+1e-14,"ok":True,"ticks":123})=={"x":1.,"ok":True,"ticks":123}
    assert rounded_state({"x":1.+1e-9})!={"x":1.}


def test_numeric_comparison_preserves_discrete_facts_and_physical_differences():
    from topogym.benchmark.evidence import equivalent_states
    assert equivalent_states({"x":1.,"success":False},{"x":1.+1e-11,"success":False})
    assert not equivalent_states({"x":1.},{"x":1.00001})
    assert not equivalent_states({"steps":1},{"steps":2})
    assert not equivalent_states({"success":False},{"success":True})
    assert equivalent_states({"contacts":[{"link":1,"force":1.},{"link":1,"force":2.}]},
                             {"contacts":[{"link":1,"force":2.+1e-11},{"link":1,"force":1.-1e-11}]})


def test_numeric_archive_no_pickle_or_extra_members(tmp_path):
    path=tmp_path/"t.npz"
    np.savez(path,actions=np.zeros((2,3)),physics_steps=np.array([10,10],dtype=np.int64),identity=np.array("a"*64),initial=np.array("b"*64))
    assert load_trajectory(path)[0].shape==(2,3)
    np.savez(path,actions=np.array([object()]),physics_steps=np.array([10],dtype=np.int64),identity=np.array("a"*64),initial=np.array("b"*64))
    with pytest.raises(ValueError): load_trajectory(path)
    np.savez(path,actions=np.zeros((2,3)),physics_steps=np.ones(2),identity=np.array("a"*64),initial=np.array("b"*64),extra=np.array(1))
    with pytest.raises(ValueError): load_trajectory(path)


def test_missing_evidence_clears_planted_reward(tmp_path):
    instance=tmp_path/"instance.json";write_json(instance,{})
    logs=tmp_path/"logs";logs.mkdir()
    target=tmp_path/"do-not-delete";target.write_text("safe")
    (logs/"reward.txt").symlink_to(target)
    metrics=grade(instance,tmp_path/"missing",logs)
    assert metrics["success"]==0 and metrics["missing_trajectory"]==1
    assert (logs/"reward.txt").read_text()=="0\n" and target.read_text()=="safe"
    assert all(type(x) in (int,float) for x in json.loads((logs/"reward.json").read_text()).values())


@pytest.mark.parametrize("damage",[None,"replay_state","live_missing","trajectory","unfinished"])
def test_grader_requires_replay_files_and_matches_every_identity(tmp_path,damage):
    import hashlib
    instance=tmp_path/"instance.json";config={"mode":"limited"};write_json(instance,config)
    evidence=tmp_path/"data";evidence.mkdir()
    trajectory=evidence/"trajectory.npz"
    np.savez(trajectory,actions=np.zeros((1,2)),physics_steps=np.array([10],dtype=np.int64),identity=np.array(digest(config)),initial=np.array("a"*64))
    state={"joint_position":[.1,.2],"solved":True,"physics_steps":10}
    result=dict(instance_sha256=digest(config),initial_sha256="a"*64,final_sha256=digest(state),final_raw_sha256=digest(state),
        n_actions=1,sim_steps=10,success=True,scoring_eligible=True,reason="success")
    for i in (1,2):
        write_json(evidence/f"replay-{i}/result.json",result)
        write_json(evidence/f"replay-{i}/final-state.json",state)
    write_json(evidence/"live.json",result)
    write_json(evidence/"live/final-state.json",state)
    final=dict(finalized=True,grader_error=0,instance_sha256=digest(config),trajectory_sha256=hashlib.sha256(trajectory.read_bytes()).hexdigest(),
        replays=[result,result],live=result,deterministic=True,replay_consistent=True,success=True,
        comparison={"algorithm":"si-numeric-v1","atol":1e-9,"rtol":1e-9})
    if damage=="replay_state":write_json(evidence/"replay-2/final-state.json",dict(state,joint_position=[.2,.4]))
    if damage=="live_missing":(evidence/"live.json").unlink()
    if damage=="trajectory":trajectory.write_bytes(b"bad")
    if damage=="unfinished":final["finalized"]=False
    write_json(evidence/"final.json",final)
    metrics=grade(instance,evidence,tmp_path/"logs")
    assert metrics["success"]==int(damage is None)
    assert metrics["grader_error"]==int(damage is not None)


def test_disk_history_rewinds_every_tick_without_reusing_ids(local_env):
    local_env._config=replace(local_env.config,history_storage="disk",max_physics_steps=None)
    local_env.reset(seed=11)
    initial=local_env.state_history[0].ref
    local_env.step({"target":1.})
    past=local_env.state_history[-1].ref
    local_env.step({"target":2.})
    old_last=local_env.state_history[-1].ref
    local_env.privileged.rewind_to(initial)
    assert len(local_env.state_history)==1
    with pytest.raises(ValueError): local_env.privileged.rewind_to(past)
    local_env.step({"target":1.})
    assert local_env.state_history[-1].state_id > old_last.state_id
    assert local_env._history._spool.latest is not None


def test_disk_history_has_no_short_physics_cap(local_env):
    local_env._config=replace(local_env.config,history_storage="disk",max_physics_steps=None)
    local_env.reset(seed=11)
    for _ in range(6):
        _,_,_,truncated,_=local_env.step({"target":0.})
        assert not truncated
    assert local_env.state_history[-1].physics_step==18
