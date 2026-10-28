"""Repair campaigns preserve selected attempts, provider provenance and native settings."""
import csv
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("action_repair", Path(__file__).parents[1] / "tools/action_repair.py")
repair = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(repair)


def test_extra_retry_requires_matching_episode_and_investigated_remediation(tmp_path):
    entry = {"index": 1463, "old_run_sha256": "old-manifest"}
    assert repair.infrastructure_retry_authorization(tmp_path, entry) is None
    implementation = tmp_path / "action_repair_rate_limit.py"
    implementation.write_text("# provider transport cooldown\n")
    authorization = {"max_attempts": 4, "cause": "provider_rate_limit",
                     "old_run_sha256": "old-manifest", "remediation_sha256": repair.digest(implementation),
                     "investigation": "Observed Azure token limits; existing native retries exhausted before reset."}
    record = tmp_path / "infrastructure_retry_authorizations.json"
    record.write_text(json.dumps({"1463": authorization}))
    assert repair.infrastructure_retry_authorization(tmp_path, entry) == authorization
    assert repair.infrastructure_retry_authorization(tmp_path, {**entry, "index": 1464}) is None
    with pytest.raises(ValueError, match="Invalid"):
        repair.infrastructure_retry_authorization(tmp_path, {**entry, "old_run_sha256": "changed"})
    implementation.write_text("# unverified implementation\n")
    with pytest.raises(ValueError, match="Invalid"):
        repair.infrastructure_retry_authorization(tmp_path, entry)


def csv_file(path, rows):
    with path.open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_selection_deduplicates_actions_without_changing_selected_attempt(tmp_path, monkeypatch):
    monkeypatch.setattr(repair, "EXPECTED", {"codex_r1": (2, 1)})
    old = repair.OLD_ROOT / "suite/results/shard-0001/scene_ep1_bed/rollout_00/experiment_runs/run_chosen"
    error = dict(label="codex_r1", shard="shard-0001", transcript_path=str(old / "native/log.jsonl"),
                 step_1based="1", tool="walk_forward", raw_action="Walk forward normal",
                 applied_action="Walk<forward><slow>", explicit_intent="normal", applied="slow", native_line="4")
    errors = tmp_path / "errors.csv"
    csv_file(errors, [error, {**error, "step_1based": "2"}])
    diagnostics = tmp_path / "diagnostics.csv"
    row = dict(label="codex_r1", shard="shard-0001", run=str(old), scene="scene", episode="1", target="bed")
    csv_file(diagnostics, [row, {**row, "label": "pi_r1"}])
    plan = repair.build_plan(errors, diagnostics, tmp_path / "own")
    assert len(plan["entries"]) == 1
    assert plan["entries"][0]["original_run"] == str(old)
    assert plan["entries"][0]["destination"].startswith(str(tmp_path / "own"))
    assert len(plan["entries"][0]["mismatches"]) == 2
    assert plan["provider_change"]["to"] == "Azure OpenAI"
    csv_file(diagnostics, [row, row])
    with pytest.raises(ValueError, match="Ambiguous"):
        repair.build_plan(errors, diagnostics)


@pytest.mark.parametrize("effort,cap", [("medium", None), ("medium", 50), ("max", 50)])
def test_provider_override_keeps_native_experiment_conditions(effort, cap):
    original = {"model_config": {"model": "copilot/gpt-6-astra", "base_url_env": "MAGPIE_BASE_URL",
                                 "api_key_env": "MAGPIE_API_KEY", "send_max_tokens": False,
                                 "reasoning_effort": "medium", "temperature": 0},
                "harness_config": {"codex_command": ["old", "app-server"], "reasoning_effort": effort,
                                   "context_window": 131072, "timeout_seconds": 7200,
                                   "responses_base_url_env": "MAGPIE_BASE_URL", "allow_http": True,
                                   "auth": "bearer", "api_key_env": "MAGPIE_API_KEY"}}
    if cap is not None:
        original["harness_config"]["max_images_per_request"] = cap
    before = deepcopy(original)
    model, native = repair.azure_settings(original, Path("/new/launcher"))
    assert original == before
    assert model["model"] == "gpt-6-astra" and model["send_max_tokens"] is False
    assert native["reasoning_effort"] == effort
    assert native.get("max_images_per_request") == cap
    assert native["timeout_seconds"] == 7200 and native["context_window"] == 131072
    assert native["auth"] == "azure" and native["allow_http"] is False
    assert "responses_base_url_env" not in native and "base_url_env" not in model


def test_backport_keeps_prompt_and_other_methods_byte_identical():
    old = 'PROMPT = "Sit once means 0.5s"\nclass A:\n    def call(self):\n        return "wrong"\n\n    def plan(self):\n        return PROMPT\n'
    new = 'PROMPT = "different"\nclass A:\n    def call(self):\n        return "fixed"\n\n    def plan(self):\n        return "changed"\n'
    assert repair.replace_function(old, new, "call", "A") == old.replace('return "wrong"', 'return "fixed"')


def test_evidence_requires_matching_raw_and_executed_action(tmp_path):
    events = [
        {"event": "span.start", "event_id": "start", "name": "action.normalize", "step": 0,
         "span_id": "span", "data": {"input": {"action_name": "Turn right 90"}}},
        {"event": "span.end", "event_id": "end", "name": "action.normalize", "step": 0,
         "span_id": "span", "data": {"status": "completed", "output": {"action_name": "Turn<left><90>"}}},
    ]
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    entry = {"source_run": str(tmp_path), "mismatches": [
        {"step_1based": "1", "raw_action": "Turn right 90", "applied_action": "Turn<left><90>"}]}
    original_bytes = path.read_bytes()
    assert repair.verify_evidence(entry) == [{"span_id": "span", "start_event_id": "start", "end_event_id": "end"}]
    entry["mismatches"][0]["applied_action"] = "Turn<right><90>"
    with pytest.raises(ValueError, match="not found"):
        repair.verify_evidence(entry)
    assert path.read_bytes() == original_bytes


def test_asset_relocation_preserves_episode_and_requires_recorded_bytes(tmp_path):
    dataset = tmp_path / "owned"
    scene = dataset / "scenes/scene.scene_instance.json"
    scene.parent.mkdir(parents=True)
    scene.write_text('{"objects": [1, 2]}')
    config = dataset / "config.json"
    config.write_text('{"scenes": "scenes"}')
    old_root = Path("/unreadable/coauthor/dataset")
    episode = {"scene_id": str(old_root / "scenes" / scene.name),
               "scene_dataset_config": str(old_root / config.name), "instruction": "Sit on the bed",
               "init_yaw": 90, "goals": [{"position": [1, 2, 3]}], "max_steps": 100}
    metadata = {"episode": episode}
    before = deepcopy(metadata)
    saved = {"assets": {"scene_instance": {"path": episode["scene_id"], "sha256": repair.digest(scene)},
                         "scene_dataset_config": {"path": episode["scene_dataset_config"],
                                                   "sha256": repair.digest(config)}}}
    relocated, mapping = repair.relocate_episode(metadata, saved, dataset)
    assert metadata == before
    assert relocated == {**episode, "scene_id": str(scene), "scene_dataset_config": str(config)}
    assert {row["field"] for row in mapping} == {"scene_id", "scene_dataset_config"}
    scene.write_text('{"objects": [99]}')
    with pytest.raises(ValueError, match="differs from the original"):
        repair.relocate_episode(metadata, saved, dataset)


def test_report_accepts_valid_task_failure_and_leaves_old_results_untouched(tmp_path, monkeypatch):
    monkeypatch.setattr(repair, "EXPECTED", {"codex_r1": (1, 1)})
    destination = tmp_path / "repair"
    old = tmp_path / "old/run.json"
    old.parent.mkdir()
    old.write_text("original error evidence")
    plan = {"provider_change": {"to": "Azure"}, "entries": [{"cohort": "codex_r1", "shard": "shard-0",
            "destination": str(destination), "original_run": str(old.parent)}]}
    repair.write(tmp_path / "plan.json", plan)
    repair.write(destination / "validated_result.json", {"result": {"task_success": False, "run": "new"}})
    result = repair.campaign_report(tmp_path / "plan.json")
    assert result["counts"]["codex_r1"]["validated"] == 1
    assert result["counts"]["codex_r1"]["successes"] == 0
    assert old.read_text() == "original error evidence"


def test_replacement_postprocess_requires_enabled_policy_and_propagates_failure(tmp_path, monkeypatch):
    plan = tmp_path / 'prepared_plan.json'
    calls = []
    monkeypatch.setattr(repair.subprocess, 'run', lambda command, check: calls.append((command, check)))
    repair.replace_validated_if_enabled(plan, 3)
    assert not calls
    repair.write(tmp_path / 'replacement_policy.json', {'replace_owned_results': True})
    repair.replace_validated_if_enabled(plan, 3)
    assert calls == [([repair.sys.executable, str(tmp_path / 'action_repair_replace.py'),
                       str(plan), '--index', '3', '--apply'], True)]
    def failed(command, check):
        raise repair.subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(repair.subprocess, 'run', failed)
    with pytest.raises(repair.subprocess.CalledProcessError):
        repair.replace_validated_if_enabled(plan, 3)


def shared_quota(used=100, reserved=70, soft=200, hard=220):
    return ('mmlsquota:fileset:HEADER:quotaType:name:blockUsage:blockQuota:blockLimit:blockInDoubt:filesUsage:filesQuota:filesLimit:filesInDoubt:\n'
            f'mmlsquota:fileset:0:FILESET:sata1-scrubbed:{used}:{soft}:{hard}:{reserved}:10:100:110:5:\n')


def test_shared_capacity_subtracts_reservations_and_uses_strictest_limit():
    value = repair.parse_shared_fileset_capacity(shared_quota(), 'sata1-scrubbed')
    assert value['free_bytes'] == 30 * 1024
    assert value['free_files'] == 85
    assert repair.parse_shared_fileset_capacity(shared_quota(reserved=130), 'sata1-scrubbed')['free_bytes'] == 0
    assert repair.parse_shared_fileset_capacity(shared_quota(soft=0), 'sata1-scrubbed')['free_bytes'] == 50 * 1024


@pytest.mark.parametrize('output', ['', shared_quota() + shared_quota().splitlines()[1], shared_quota().replace('sata1-scrubbed', 'another-fileset')])
def test_shared_quota_missing_or_ambiguous_fails_closed(output):
    with pytest.raises(OSError):
        repair.parse_shared_fileset_capacity(output, 'sata1-scrubbed')


def test_shared_capacity_blocks_launch_before_paid_work(monkeypatch):
    monkeypatch.setattr(repair.subprocess, 'check_output', lambda *a, **k: shared_quota())
    monkeypatch.setenv('HUMANCLAW_GPFS_FILESET', 'sata1-scrubbed')
    monkeypatch.setenv('HUMANCLAW_MIN_FREE_BYTES', str(31 * 1024))
    monkeypatch.setenv('HUMANCLAW_MIN_FREE_FILES', '20')
    with pytest.raises(OSError, match='Insufficient shared'):
        repair.check_shared_fileset_storage()
    monkeypatch.setenv('HUMANCLAW_MIN_FREE_BYTES', str(30 * 1024))
    assert repair.check_shared_fileset_storage()['free_bytes'] == 30 * 1024
