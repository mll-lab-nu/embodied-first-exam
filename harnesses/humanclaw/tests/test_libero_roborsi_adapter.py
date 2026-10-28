"""Optional upstream integration checks (run with the pinned RoboRSI installed)."""
from types import SimpleNamespace

import pytest

pytest.importorskip("roborsi")


def test_roborsi_adapter_targets_engineers_lazy_import(monkeypatch, tmp_path):
    monkeypatch.setenv("ROBORSI_HOME", str(tmp_path / "roborsi_home"))
    monkeypatch.setenv("ROBORSI_RUN_MODE", "frozen")
    monkeypatch.setenv("ROBORSI_ROLE_SESSION", "0")
    import roborsi.embodied.agent_loop as agent_loop
    import roborsi.embodied.agent_loop.rollout as rollout
    import roborsi.channels.core.agent as coordinator
    from humanclaw_bench.libero.adapters import run_roborsi
    from humanclaw_bench.libero.backend import MockBackend
    from humanclaw_bench.libero.protocol import ToolService

    backend = MockBackend()
    backend.env = SimpleNamespace(take_snapshot=lambda: "prepared-observation", reset=lambda seed: "reset")
    backend.seed, backend.task = 0, "mock/0"
    backend.context = SimpleNamespace(last_image_path=None)
    bridge = ToolService(backend, "roborsi-adapter-check", tmp_path)
    seen = {}
    def original_loop(*args, **kwargs):
        seen.update(kwargs)
        return "native-loop-result"
    monkeypatch.setattr(rollout, "run_rollout", original_loop)
    original_backend = agent_loop.get_backend
    def coordinator_stub(**kwargs):
        # This is the same lazy import site used by upstream Engineer.execute.
        from roborsi.embodied.agent_loop.rollout import run_rollout
        with agent_loop.get_backend("libero-pro").make_env("mock/0") as env:
            assert env.reset(0) == "prepared-observation"
            assert run_rollout(env, instruction="upstream plan", tool_budget=5) == "native-loop-result"
            result, obs = rollout._dispatch_with_timeout(SimpleNamespace(), {
                "tool": "move", "args": {"delta": 2, "request_id": "m1", "observation_id": 0}})
            assert result["request_status"] == "completed"
            assert obs == "prepared-observation"
        return {"native_coordinator": True}
    monkeypatch.setattr(coordinator, "run_atomic_episode", coordinator_stub)
    try:
        result = run_roborsi(bridge, None, {"model": "test"})
        assert seen["instruction"].startswith("upstream plan")
        assert "COMMON TOOL PROTOCOL" in seen["instruction"]
        assert seen["tool_budget"] == 5
        assert backend.position == 2
        assert rollout.run_rollout is original_loop
        assert agent_loop.get_backend is original_backend
        assert backend.env.reset(0) == "reset"
        assert result["upstream_result"]["native_coordinator"]
    finally:
        bridge.shutdown()
