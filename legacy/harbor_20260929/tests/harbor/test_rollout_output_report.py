"""Outcome, budget and missing evidence must remain distinct in terminal output."""
import json

from harbor_runners.collect import atomic_json
from harbor_runners.rollout_output_report import summarize, format_summary, main


def example_run(tmp_path, *, mode="observed", physical_success=False):
    run = tmp_path / "run"
    archive = tmp_path / "archive"
    instance = {"evaluation":"task_success", "mode":"unlimited",
                "simulator":{"task_id":"cube_pick_place", "seed":0, "control_mode":"EE_ABS"}}
    atomic_json(run / "experiment.resolved.json", {
        "instances":[instance], "attempts":1, "usage":{"mode":mode},
        "model_connection":{"full_model_name":"openrouter/test", "provider_id":"openrouter",
                            "opencode_version":"1.18.33"}})
    usage = {"mode":"observed", "limits":{"input_tokens":30000,"output_tokens":10000},
        "usage":{"input_tokens":32840,"output_tokens":704}, "input_tokens":32840,"output_tokens":704,
        "overshoot":{"input_tokens":2840,"output_tokens":0}, "request_count":4,"in_flight_requests":0,
        "usage_complete":True, "stop":{"reason":"budget_exceeded","dimensions":["input_tokens"],
            "decision_monotonic_ns":1_000_000_000}}
    item = {"status":"complete", "archive":str(archive), "pipeline_passed":mode=="off",
        "verification":{"evaluation":"task_success", "task_success":physical_success,
            "reward":0, "evidence_complete":True,"segments":0,"scoring_eligible":mode=="off"}}
    if mode != "off":
        item.update(usage=usage, budget_qualified=False, failure_reason="budget_exceeded",
            stop_timings={"agent_stopped_monotonic_ns":1_140_000_000,
                          "worker_stopped_monotonic_ns":1_256_000_000})
    atomic_json(run / "rollout_index.json", {"expected_trials":1,"collected_trials":1,
        "pipeline_passed":mode=="off", "trials":{"trial-1":item}})
    atomic_json(archive / "instance.json", instance)
    atomic_json(archive / "session_final.json", {"episode_id":"episode-1"})
    atomic_json(archive / "report.json", {"episode_id":"episode-1", "segments":[
        {"result":{"segment_id":0,"control_steps":5,"simulated_duration_s":.125}}]})
    return run, archive


def test_input_stop_reports_actual_usage_final_limits_and_initial_only_episode(tmp_path):
    run, archive = example_run(tmp_path)
    before = {p:p.read_bytes() for p in archive.iterdir()}
    summary = summarize(run)
    episode = summary["episodes"][0]
    assert episode["policy_segments"]==0 and episode["policy_control_steps"]==0
    assert episode["initial_control_steps"]==5 and episode["simulated_duration_s"]==.125
    assert episode["agent_stop_delay_ms"]==140 and episode["execution_stop_delay_ms"]==256
    text = format_summary(summary)
    assert "Input: 32,840 / 30,000 (over by 2,840)" in text
    assert "Output: 704 / 10,000" in text
    assert "budget_exceeded [input_tokens]" in text and "Model requests: 4" in text
    assert "initial=5, policy=0" in text and "Simulated: 0.125s" in text
    assert "agent +140.0ms" in text and "execution +256.0ms" in text
    assert all(p.read_bytes()==data for p,data in before.items())


def test_physical_success_does_not_hide_budget_failure(tmp_path):
    run, _ = example_run(tmp_path, physical_success=True)
    summary = summarize(run)
    text = format_summary(summary)
    assert "Task success: yes | Reward: 0 | Pipeline: FAIL" in text
    assert "Token budget: FAIL" in text and summary["budget_success_rate"]==0


def test_successful_policy_steps_and_updated_budget_are_reported(tmp_path):
    run, archive = example_run(tmp_path, physical_success=True)
    index = json.loads((run / "rollout_index.json").read_text())
    item = index["trials"]["trial-1"]
    item.update(pipeline_passed=True, budget_qualified=True, failure_reason=None, stop_timings={})
    item["usage"].update(stop=None, limits={"input_tokens":60000,"output_tokens":10000},
                         overshoot={"input_tokens":0,"output_tokens":0})
    item["verification"].update(reward=1, segments=1, scoring_eligible=True)
    index["pipeline_passed"] = True
    atomic_json(run / "rollout_index.json", index)
    atomic_json(archive / "report.json", {"segments":[
        {"result":{"segment_id":0,"control_steps":5,"simulated_duration_s":.125}},
        {"result":{"segment_id":1,"control_steps":100,"simulated_duration_s":2.5}}]})
    text = format_summary(summarize(run))
    assert "Input: 32,840 / 60,000" in text and "over by" not in text
    assert "Task success: yes | Reward: 1 | Pipeline: PASS" in text
    assert "initial=5, policy=100" in text and "Simulated: 2.625s" in text


def test_missing_usage_and_archive_remain_unknown_instead_of_zero(tmp_path):
    run, archive = example_run(tmp_path)
    index = json.loads((run / "rollout_index.json").read_text())
    index["trials"] = {"trial-1":{"status":"incomplete", "pipeline_passed":False,
        "budget_qualified":False, "failure_reason":"usage_unavailable", "verification":{"reward":0}}}
    atomic_json(run / "rollout_index.json", index)
    summary = summarize(run)
    episode = summary["episodes"][0]
    assert episode["policy_segments"] is None and episode["control_steps"] is None
    assert episode["usage"]["input_tokens"] is None
    text = format_summary(summary)
    assert "Input: unknown / unknown" in text
    assert "Task success: unknown" in text and "Simulated: unknown" in text
    assert "usage_unavailable" in text


def test_scripted_off_does_not_claim_zero_model_usage(tmp_path):
    run, _ = example_run(tmp_path, mode="off")
    text = format_summary(summarize(run))
    assert "Token budget: off (usage not measured)" in text and "Input:" not in text


def test_report_cli_keeps_default_json_and_offers_text_without_model_calls(tmp_path, capsys):
    run, _ = example_run(tmp_path)
    main(["--run",str(run)])
    summary = json.loads(capsys.readouterr().out)
    assert summary["episodes"][0]["episode_id"]=="episode-1"
    main(["--run",str(run),"--format","text"])
    assert "TopoGym episode summary" in capsys.readouterr().out
