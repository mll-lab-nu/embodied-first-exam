"""G2: real engine time limits, failed ticks, recovery and repeated lifecycle."""
from pathlib import Path
import os
import traceback
import pytest
from topogym.simulator import Env, SimulatorConfig
from runtime_evidence import RuntimeEvidence

pytestmark = [pytest.mark.genesis, pytest.mark.render]


@pytest.mark.parametrize("robot_id", ["aloha", "panda_robotiq"])
def test_stability(robot_id):
    root = Path(os.environ["TOPOGYM_TEST_OUTPUT"])
    cfg = SimulatorConfig(task_id="cast_coil" if robot_id == "aloha" else "hedgehog_in_cage",
                          robot_id=robot_id, enable_privileged=True, max_physics_steps=17)
    evidence = RuntimeEvidence(root / f"stability_{robot_id}", f"stability_{robot_id}", cfg)
    error = None
    env = Env(cfg)
    resources = []
    try:
        for cycle in range(10):
            with evidence.stage(f"reset_cycle_{cycle}") as stage:
                obs, info = env.reset(seed=cycle % 2)
                evidence.sample(env, obs, info, label="initial")
                old_handle = env.interaction(privileged=True)
                for i in range(2):
                    obs, _, done, truncated, info = old_handle.step({})
                    evidence.sample(env, obs, info, action={})
                    assert info["physics_steps"] == (10 if i == 0 else 7)
                assert truncated and not done and info["physics_step"] == 17
                with pytest.raises(RuntimeError):
                    old_handle.step({})
                obs, info = old_handle.rewind_to(env.state_history[0].ref)
                evidence.sample(env, obs, info, label="rewind")
                anchor = env.state_history[0].ref
                # Fail after an actual physical tick, before that tick can commit.
                advance = env._world.advance
                def failed_advance():
                    advance()
                    raise RuntimeError("injected post-integration failure")
                env._world.advance = failed_advance
                with pytest.raises(RuntimeError, match="injected"):
                    old_handle.step({})
                env._world.advance = advance
                assert len(env.state_history) == 1
                with pytest.raises(RuntimeError, match="faulted"):
                    old_handle.step({})
                obs, info = old_handle.rewind_to(anchor)
                evidence.sample(env, obs, info, label="fault_recovery")
                obs, _, done, truncated, info = old_handle.step({})
                evidence.sample(env, obs, info, label="continued", action={})
                assert not done and not truncated
                import psutil, torch
                process = psutil.Process()
                stage["resources"] = dict(rss_bytes=process.memory_info().rss, file_descriptors=process.num_fds(),
                                          cuda_allocated_bytes=torch.cuda.memory_allocated(),
                                          cuda_reserved_bytes=torch.cuda.memory_reserved())
                resources.append(stage["resources"])
                evidence.end_recording()
        with evidence.stage("bounded_resource_growth_after_warmup") as stage:
            # A bounded smoke gate, not proof against a slow long-run leak.
            limits = dict(rss_bytes=1024**3, file_descriptors=8,
                          cuda_allocated_bytes=256 * 1024**2, cuda_reserved_bytes=256 * 1024**2)
            stage["growth_limits"] = limits
            stage["observed_growth"] = {key: max(row[key] for row in resources[3:]) - resources[3][key]
                                        for key in limits}
            for key, limit in limits.items():
                assert stage["observed_growth"][key] <= limit, (key, resources)
        with evidence.stage("close_and_expired_operator"):
            env.close(); env.close()
            with pytest.raises(RuntimeError, match="expired"):
                old_handle.observe()
            assert not env.state_history
    except BaseException:
        error = traceback.format_exc()
        raise
    finally:
        try:
            evidence.close(error)
        finally:
            env.close()
