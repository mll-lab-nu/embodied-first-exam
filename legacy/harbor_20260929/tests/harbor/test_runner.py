"""Run with Python 3.12 and --confcutdir=tests/harbor; no simulator dependencies."""
import asyncio
from contextlib import nullcontext
import copy
import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

if sys.version_info < (3, 12):
    pytest.skip("Harbor tests use .venv-harbor (Python 3.12)", allow_module_level=True)
pytest.importorskip("harbor")

from harbor.agents.factory import AgentFactory
from harbor.models.job.config import JobConfig
from harbor.models.task.task import Task
from harbor.models.trial.config import AgentConfig
from harbor.trial.trial import Trial
from harbor_runners.agents.credentials import selected_secrets, redact, redact_logs
from harbor_runners.collect import collect, verify_archive
from harbor_runners.config import load_config, validate
from harbor_runners.preflight import check
from harbor_runners.task_generator import file_hash, prepare as native_prepare, verify_frozen, write_json
from harbor_runners.usage_bridge import validate_usage
from harbor_runners.hooks import cleanup, recover, run_label
from harbor_runners.rollout_output_report import summarize

ROOT = Path(__file__).resolve().parents[2]


def prepare(config, root, run_id):
    return native_prepare(config, root, run_id, scripted_scenario="normal")


@pytest.fixture
def config():
    return load_config(ROOT / "configs/harbor/experiments/smoke_scripted.yaml")


def test_native_task_discovery_and_attempt_expansion(config, tmp_path):
    config["instances"].append({**copy.deepcopy(config["instances"][0]), "name": "second"})
    config.update(attempts=3, concurrency=2)
    run = prepare(config, tmp_path, "example")
    manifest = verify_frozen(run)
    assert manifest["task_count"] == 2 and manifest["expected_trials"] == 6
    job = JobConfig.model_validate_json((run / "job.json").read_text())
    tasks = asyncio.run(job.datasets[0].get_task_configs())
    assert len(tasks) == 2 and job.n_attempts == 3 and job.n_concurrent_trials == 2
    for task_config in tasks:
        task = Task(task_config.path)
        assert task.config.agent.user == "agent"
        assert task.config.verifier.user == "root"
        assert task.config.environment.healthcheck.command.endswith("ready --check-initial")
        assert task.config.environment.docker_image == config["image"]
        assert task.config.artifacts[0].destination == "topogym-rollout"
        compose = yaml.safe_load((task_config.path / "environment/docker-compose.yaml").read_text())
        mount = compose["services"]["main"]["volumes"][0]
        assert mount["read_only"] and Path(mount["source"]).exists()
        assert "topogym-rollout-worker" in compose["services"]["main"]["command"][-1]
        assert not (task_config.path / "environment/topogym").exists()
        device = compose["services"]["main"]["deploy"]["resources"]["reservations"]["devices"][0]
        assert device == {"driver": "nvidia", "capabilities": ["gpu"], "count": 1}
    assert check(run, docker=False)["trials"] == 6


def test_frozen_inputs_cannot_be_reused_or_modified(config, tmp_path):
    run = prepare(config, tmp_path, "frozen")
    with pytest.raises(FileExistsError):
        prepare(config, tmp_path, "frozen")
    file = next((run / "harbor_tasks").glob("*/instruction.md"))
    file.chmod(0o644)
    file.write_text("changed")
    with pytest.raises(ValueError, match="changed"):
        verify_frozen(run)


def test_new_task_after_prepare_is_rejected(config, tmp_path):
    run = prepare(config, tmp_path, "frozen")
    extra = run / "harbor_tasks/extra/instruction.md"
    extra.parent.mkdir()
    extra.write_text("injected")
    with pytest.raises(ValueError, match="changed"):
        verify_frozen(run)


@pytest.mark.parametrize("bad", [{"mode": "strict"}, {"mode": "observed"},
    {"mode": "posthoc"}, {"mode": "off", "total_tokens": 20000000}, {"input_tokens": 50_000_000}])
def test_no_silent_token_budget_downgrade(config, tmp_path, bad):
    config["usage"] = bad
    with pytest.raises(ValueError, match="not enforced"):
        prepare(config, tmp_path, "tokens")
    assert not (tmp_path / "runs/harbor/tokens").exists()


def test_usage_off_reports_unknown_not_zero():
    result = validate_usage({"mode": "off"})
    assert result["input_tokens"] is None and result["output_tokens"] is None
    assert result["enforcement"] == "not_enforced"


def test_credentials_are_references_not_values(config, tmp_path, monkeypatch):
    secret = "test-credential-value-not-for-files"
    monkeypatch.setenv("TOPOGYM_MODEL_API_KEY", secret)
    config.update(model="openai/test-model", usage={"mode":"observed"})
    run = native_prepare(config, tmp_path, "credentials")
    for path in run.rglob("*"):
        if path.is_file():
            assert secret not in path.read_text()
    job = json.loads((run / "job.json").read_text())
    assert job["agents"][0]["env"] == {}
    monkeypatch.delenv("TOPOGYM_MODEL_API_KEY")
    with pytest.raises(ValueError, match="API key"):
        check(run, docker=False)


def test_plaintext_key_in_kwargs_is_rejected():
    config=load_config()
    config["agent"]={"name":"codex","kwargs":{"api_key":"secret"}}
    with pytest.raises(ValueError, match="Unknown experiment field"):
        validate(config)


def test_agent_neutral_secret_redaction(tmp_path, monkeypatch):
    monkeypatch.setenv("SOME_PROVIDER_TOKEN", "test-secret-value")
    secrets = selected_secrets({"TOPOGYM_MODEL_API_KEY": "test-secret-value"})
    path = tmp_path / "jobs/trial/agent/log.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text('{"accidental":"test-secret-value"}\n')
    redact_logs(tmp_path, secrets)
    assert json.loads(path.read_text())["accidental"] == "[REDACTED]"
    assert redact("test-secret-value", secrets) == "[REDACTED]"


def test_difficulty_seed_sweep_uses_existing_canonical_catalog(tmp_path):
    from harbor_runners.config import expand
    config = load_config(ROOT / "configs/harbor/experiments/cast_coil_rollout.yaml")
    config["usage"] = {"mode": "off"}
    expand(config, task="cast_coil", difficulties=["easy", "medium", "hard"], seeds=[0, 1])
    config["attempts"] = 3
    run = prepare(config, tmp_path, "sweep")
    manifest = verify_frozen(run)
    assert manifest["task_count"] == 6 and manifest["expected_trials"] == 18
    resolved = json.loads((run / "experiment.resolved.json").read_text())
    assert {i["simulator"]["variation_id"] for i in resolved["instances"]} == {
        "cast_coil_easy", "cast_coil_medium", "cast_coil_hard"}
    assert all(len(i["catalog"]["sha256"]) == 64 for i in resolved["instances"])
    config["instances"][0]["simulator"]["variation_id"] = "nonexistent"
    with pytest.raises(ValueError, match="unavailable"):
        prepare(config, tmp_path, "bad-sweep")


def test_gpu_device_selection(config, tmp_path):
    config["gpu_devices"] = ["2"]
    run = prepare(config, tmp_path, "gpu")
    compose = yaml.safe_load(next((run / "harbor_tasks").glob("*/environment/docker-compose.yaml")).read_text())
    device = compose["services"]["main"]["deploy"]["resources"]["reservations"]["devices"][0]
    assert device["device_ids"] == ["2"] and "count" not in device


@pytest.mark.parametrize("gpus,devices", [(0, None), (1, None), (1, ["0"]), (2, ["0", "1"])])
def test_generated_task_constructs_native_docker_environment(config, tmp_path, gpus, devices):
    """Exercise Harbor's runtime capability gate, not just its TOML schema."""
    from harbor.environments.docker.docker import DockerEnvironment
    from harbor.models.trial.paths import TrialPaths

    config.update(gpus=gpus, gpu_devices=devices)
    run = prepare(config, tmp_path, "docker-capabilities")
    task = Task(next((run / "harbor_tasks").iterdir()))
    environment = DockerEnvironment(
        environment_dir=task.paths.environment_dir,
        environment_name=task.short_name,
        session_id="gpu-contract",
        trial_paths=TrialPaths(trial_dir=tmp_path / "trial"),
        task_env_config=task.config.environment,
    )
    assert environment.capabilities.docker_compose
    # Harbor 0.23.0 Docker does not implement generic GPU allocation. The
    # frozen Compose request must still preserve the actual GPU requirement.
    assert task.config.environment.gpus is None
    assert task.config.metadata["topogym_gpus"] == gpus
    compose = yaml.safe_load((task.paths.environment_dir / "docker-compose.yaml").read_text())
    service = compose["services"]["main"]
    if gpus:
        assert service["runtime"] == "nvidia"
        assert service["environment"]["NVIDIA_DRIVER_CAPABILITIES"] == "all"
        reservation = service["deploy"]["resources"]["reservations"]["devices"][0]
        assert reservation == dict(driver="nvidia", capabilities=["gpu"],
                                   **({"device_ids": devices} if devices else {"count": gpus}))
    else:
        assert "deploy" not in service
        assert "runtime" not in service


def test_scripted_driver_uses_same_native_task_contract(config,tmp_path):
    run=prepare(config,tmp_path,"scripted-contract")
    resolved=json.loads((run/"job.json").read_text())["agents"][0]
    cls = AgentFactory.get_agent_class_from_config(AgentConfig(**resolved))
    assert cls.name() == "topogym-scripted"


@pytest.mark.parametrize("edit", [
    lambda c: c.update(concurrency=0),
    lambda c: c["instances"][0]["simulator"].update(seed=True),
    lambda c: c["instances"][0]["simulator"].update(work_dir="/agent/path"),
    lambda c: c["instances"][0].update(state_fields=["world"]),
    lambda c: c["instances"][0].update(name="../../escape"),
])
def test_invalid_config_rejected_before_writing(config, tmp_path, edit):
    edit(config)
    with pytest.raises((ValueError, TypeError)):
        prepare(config, tmp_path, "invalid")
    assert not (tmp_path / "runs/harbor/invalid").exists()


def test_native_prepare_waits_for_health_before_agent_setup():
    events = []
    async def event(name):
        events.append(name)
    owner = SimpleNamespace(_task_trajectory_error=None, user_agent=None,
        _setup_agent_environment=lambda: event("environment"),
        _upload_injected_skills=lambda: event("skills"), _setup_agent=lambda: event("agent_setup"),
        task=SimpleNamespace(config=SimpleNamespace(agent=SimpleNamespace(user="agent"))),
        result=SimpleNamespace(), agent=SimpleNamespace(to_agent_info=lambda: {}),
        agent_environment=SimpleNamespace(run_healthcheck=lambda: event("initial_ready"),
            with_default_user=lambda user: nullcontext()))
    asyncio.run(Trial._prepare(owner))
    assert events == ["environment", "initial_ready", "skills", "agent_setup"]


def test_failed_initial_health_prevents_agent_setup():
    events = []
    async def setup():
        events.append("environment")
    async def fail():
        raise RuntimeError("RGB unavailable")
    owner = SimpleNamespace(_task_trajectory_error=None, _setup_agent_environment=setup,
        agent_environment=SimpleNamespace(run_healthcheck=fail))
    with pytest.raises(RuntimeError, match="RGB unavailable"):
        asyncio.run(Trial._prepare(owner))
    assert events == ["environment"]


def fake_export(run, config, name="trial-1", *, exception=None):
    trial = run / "jobs/job" / name
    source = trial / "artifacts/topogym-rollout"
    source.mkdir(parents=True)
    write_json(trial / "result.json", {"exception_info": exception})
    write_json(source / "instance.json", config["instances"][0])
    write_json(source / "verification.json", {"pipeline_passed": True, "reward": 1,
        "task_success": False, "evaluation": "pipeline_smoke"})
    (source / "segment_1.mp4").write_bytes(b"fixture bytes; not a real video")
    write_json(source / "archive_manifest.json", {"files": {
        str(p.relative_to(source)): {"sha256": file_hash(p), "size_bytes": p.stat().st_size}
        for p in source.iterdir()}})
    return source


def test_collect_verifies_moves_and_retries_without_duplicate_video(config, tmp_path):
    run = prepare(config, tmp_path, "collect")
    source = fake_export(run, config)
    first = collect(run, tmp_path)
    assert first["pipeline_passed"]
    destination = Path(first["trials"]["trial-1"]["archive"])
    assert not source.exists() and (destination / "segment_1.mp4").exists()
    assert not list((run / "jobs").rglob("*.mp4"))
    assert collect(run, tmp_path) == first
    assert len(list((tmp_path / "task_rollouts").rglob("*.mp4"))) == 1


def test_corrupt_export_is_retained_and_not_scored(config, tmp_path):
    run = prepare(config, tmp_path, "corrupt")
    source = fake_export(run, config)
    (source / "segment_1.mp4").write_bytes(b"truncated")
    result = collect(run, tmp_path)
    assert not result["pipeline_passed"] and source.exists()
    assert result["trials"]["trial-1"]["status"] == "incomplete"


def test_missing_export_and_harbor_error_cannot_pass(config, tmp_path):
    run = prepare(config, tmp_path, "error")
    assert not collect(run, tmp_path)["pipeline_passed"]
    fake_export(run, config, exception={"exception_type": "AgentTimeoutError"})
    result = collect(run, tmp_path)
    assert not result["pipeline_passed"]
    assert result["trials"]["trial-1"]["harbor_exception"] == "AgentTimeoutError"


def test_symlink_export_rejected(config, tmp_path):
    run = prepare(config, tmp_path, "symlink")
    source = fake_export(run, config)
    (source / "escape").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="symlink"):
        verify_archive(source)


def test_failed_move_keeps_source_and_resumes_pending_archive(config, tmp_path, monkeypatch):
    run = prepare(config, tmp_path, "move")
    source = fake_export(run, config)
    original = Path.replace
    def fail(path, target):
        if path == source:
            raise OSError("disk failure")
        return original(path, target)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", fail)
        result = collect(run, tmp_path)
    assert not result["pipeline_passed"] and source.exists()
    destination = result["trials"]["trial-1"]["archive"]
    result = collect(run, tmp_path)
    assert result["pipeline_passed"] and result["trials"]["trial-1"]["archive"] == destination


def test_cleanup_retains_unverified_or_live_containers(tmp_path, monkeypatch):
    import harbor_runners.hooks as hooks
    calls = []
    def docker(*args):
        calls.append(args)
        return "container-id\n" if args[0] == "ps" else json.dumps([{"State": {"Running": True}}])
    monkeypatch.setattr(hooks, "_docker", docker)
    assert cleanup(tmp_path, {"expected_trials": 1, "collected_trials": 0})["status"] == "retained"
    assert calls == []
    index = {"expected_trials": 1, "collected_trials": 1, "trials": {"t": {"status": "complete"}}}
    assert cleanup(tmp_path, index)["reason"] == "container_still_running"
    assert not any(args[0] == "rm" for args in calls)


def test_cleanup_only_stopped_run_labelled_objects(tmp_path, monkeypatch):
    import harbor_runners.hooks as hooks
    calls = []
    def docker(*args):
        calls.append(args)
        if args[0] == "ps": return "c1\n"
        if args[0] == "inspect": return json.dumps([{"State": {"Running": False}}])
        if args[:2] == ("network", "ls"): return "n1\n"
        return ""
    monkeypatch.setattr(hooks, "_docker", docker)
    index = {"expected_trials": 1, "collected_trials": 1, "trials": {"t": {"status": "complete"}}}
    assert cleanup(tmp_path, index)["status"] == "removed"
    assert ("rm", "-v", "c1") in calls
    assert all("--force" not in args for args in calls)
    assert any("label=" + run_label(tmp_path) in args for args in calls)


def test_summary_never_mixes_smoke_with_task_success(config, tmp_path):
    run = prepare(config, tmp_path, "summary")
    fake_export(run, config)
    collect(run, tmp_path)
    result = summarize(run)
    assert result["pipeline_smoke_trials"] == 1
    assert result["scored_task_trials"] == 0 and result["success_rate"] is None
    assert result["budget_qualified"] is None and result["token_budget_enforced"] is False


def test_container_probe_and_embedded_policies_compile():
    import ast
    script = ast.parse((ROOT / "scripts/test_harbor_pipeline.py").read_text())
    value = next(ast.literal_eval(node.value) for node in script.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "ISOLATION_CHECK" for target in node.targets))
    probe = ast.parse(value)
    for node in probe.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in {"source", "hang"} for target in node.targets):
            compile(ast.literal_eval(node.value), "container_policy.py", "exec")
