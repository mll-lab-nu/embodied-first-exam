"""Markdown comparison of evaluation outputs, read from results.jsonl only (interrupted runs are reported too)."""
import json

from vla.gym.report import table


def write_run(path, rows):
    path.mkdir()
    (path / "results.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))


def row(model, outcome, steps, error, unit, clipped=0):
    return dict(task="cast_coil", model=model, instruction_version=1, outcome=outcome, control_steps=steps,
                inference_calls=steps // 10, tracking_error_mean=error, tracking_error_unit=unit,
                clipped_actions=clipped, rollout_wall_s=60.0, execute_steps=25, control_hz_actual=50.0)


def test_one_row_per_run_with_outcome_counts_and_episode_means(tmp_path):
    write_run(tmp_path / "a", [row("pi05_base_trossen", "time_limit", 100, 0.5, "rad", 90),
                               row("pi05_base_trossen", "success", 60, 0.3, "rad", 10)])
    write_run(tmp_path / "b", [row("xvla_robotwin2", "invalid_action", 0, None, "m")])
    lines = table([tmp_path / "a", tmp_path / "b"]).splitlines()
    assert len(lines) == 4 and lines[0].startswith("| model | task | success |")
    assert lines[2] == ("| pi05_base_trossen | cast_coil | 1/2 | success 1, time_limit 1 | 50 | 25 | v1 | 80 | 8 "
                        "| 0.4 rad | 50 | 1.0 |")
    assert lines[3] == "| xvla_robotwin2 | cast_coil | 0/1 | invalid_action 1 | 50 | 25 | v1 | 0 | 0 | - | 0 | 1.0 |"


def test_rows_written_before_tracking_error_unit_are_reported_without_a_unit(tmp_path):
    old = row("pi05_droid_jointpos", "time_limit", 445, 0.049, None)
    del old["tracking_error_unit"]
    write_run(tmp_path / "old", [old])
    assert "| 0.049 |" in table([tmp_path / "old"]).splitlines()[2]
