"""The generator's self-owned family registration (artifacts FAMILY_PLUGIN.md), on a throwaway fixture family."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tomllib

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import generate  # noqa: E402


def make_family(root: Path, family: str = "fixture_plugin", oracle: str = "full") -> Path:
    folder = root / family
    (folder / "instruction").mkdir(parents=True)
    (folder / "assets/meshes").mkdir(parents=True)
    (folder / "solution").mkdir()
    (folder / "runtime.py").write_text("class Session:\n    pass\n")
    (folder / "replay.py").write_text("print('replay')\n")
    (folder / "scene.py").write_text("SCENE = 1\n")
    (folder / "demo.py").write_text("raise SystemExit('authoring only')\n")
    (folder / "assets/meshes/part.obj").write_text("v 0 0 0\n")
    (folder / "task.json").write_text(json.dumps({
        "id": family, "title": "Fixture task", "description": "A fixture.", "instruction": "Do the fixture.",
        "difficulty": "hard", "category": "fixture",
    }))
    for mode in ("privileged", "standard"):
        (folder / f"instruction/{mode}.md").write_text(
            "# DexHand: {{TITLE}}\n\n{{TASK_TEXT}}\n\n{{HANDS}}\n## Deliverable\nSave `/app/output/gen.py`; "
            "at most {{MAX_ROWS}} rows.\n")
    (folder / "README.task.md").write_text(
        "## Task\n{{TASK_TEXT}}\n\n## Difficulty\nHard.\n\n## Reference solution\nRows.\n\n"
        "## Verification\nTwin `{{TWIN}}` of `{{NAME}}` ({{MODE}}).\n\n## Details\nImage `{{IMAGE}}`.\n")
    np.savez(folder / "solution/trajectory.npz", actions=np.zeros((3, 28)), hand=np.array("sharpa"))
    manifest = {
        "schema_version": 1, "id": family, "task": "task.json",
        "runtime": {"files": ["runtime.py", "replay.py", "scene.py"], "dirs": ["assets"], "shared": ["checker.py"]},
        "hands": ["sharpa", "wuji"], "action_dim": {"sharpa": 28, "wuji": 26}, "robot": "sharpa-wave-floating",
        "max_rows": 1234,
        "instruction": {"privileged": "instruction/privileged.md", "standard": "instruction/standard.md"},
        "readme": "README.task.md",
        "solution": {"privileged": "solution/trajectory.npz", "standard": "solution/trajectory.npz"},
        "metadata": {"oracle": oracle, "keywords": ["fixture"],
                     **({} if oracle == "full" else {"oracle_evidence": "fixture evidence"})},
        "timeouts": {"replay_sec": 600},
        "compose_env": {"RCB_STARTUP_TIMEOUT_S": "600"},
    }
    (folder / "family.json").write_text(json.dumps(manifest))
    return folder


@pytest.fixture
def families(tmp_path, monkeypatch):
    root = tmp_path / "families"
    root.mkdir()
    monkeypatch.setattr(generate, "FAMILIES", root)
    monkeypatch.setattr(generate, "EXTERNAL_FAMILIES", ())
    return root


def test_plugin_pair_is_rendered(families, tmp_path):
    make_family(families)
    out = tmp_path / "tasks"
    tasks = generate.render(out, {"fixture_plugin"})
    assert sorted(t.name for t in tasks) == ["dexhand-fixture-plugin-i00-privileged", "dexhand-fixture-plugin-i00-standard"]
    priv, std = out / "dexhand-fixture-plugin-i00-privileged", out / "dexhand-fixture-plugin-i00-standard"
    meta = tomllib.loads((priv / "task.toml").read_text())["metadata"]
    assert meta["oracle"] == "full" and "oracle_evidence" not in meta
    assert meta["hands"] == ["sharpa", "wuji"] and meta["default_hand"] == "sharpa"
    # the agent's time limit is the cutoff table's DexHand row, never a family setting
    assert tomllib.loads((priv / "task.toml").read_text())["agent"]["timeout_sec"] == float(generate.CUTOFF["privileged"])
    assert json.loads((priv / "tests/grading.json").read_text())["replay_timeout_s"] == 600
    for runtime in (priv / "environment", priv / "tests", std / "environment/sim"):
        for name in ("runtime.py", "replay.py", "scene.py", "assets/meshes/part.obj", "checker.py",
                     "rcb_dexhand.py", "hands.py", "instance.json", "catalog.json"):
            assert (runtime / name).is_file(), (runtime, name)
        assert not (runtime / "demo.py").exists() and not (runtime / "family.json").exists()
    text = (priv / "instruction.md").read_text()
    assert "## Hands" in text and "`28` wide for `sharpa`" in text and "`26` wide for `wuji`" in text
    assert "at most 1234 rows." in text and "{{" not in text and text.rstrip().endswith("(`## External material` above).")
    assert "DEXHAND_HAND" in (std / "instruction.md").read_text()
    assert "Twin `dexhand-fixture-plugin-i00-standard`" in (priv / "README.md").read_text()
    compose = (std / "environment/docker-compose.yaml").read_text()
    assert "DEXHAND_HAND: ${DEXHAND_HAND:-sharpa}" in compose and 'RCB_STARTUP_TIMEOUT_S: "600"' in compose
    assert (priv / "solution/solve.sh").stat().st_mode & 0o111 and (priv / "solution/oracle.py").is_file()
    assert (std / "solution/oracle_replay.py").is_file() and (std / "solution/trajectory.npz").is_file()
    # without a per-hand solution the single-hand oracle runners are written byte for byte
    assert (priv / "solution/solve.sh").read_bytes() == (generate.SOLUTION / "solve_privileged.sh").read_bytes()
    assert (std / "solution/solve.sh").read_bytes() == (generate.SOLUTION / "solve_standard.sh").read_bytes()
    assert not (priv / "solution/wuji").exists() and not (std / "solution/wuji").exists()
    assert (priv / "tests/grade.py").read_bytes() == (generate.SHARED / "grade.py").read_bytes()
    assert (std / "environment/sim/server.py").read_bytes() == (generate.SHARED / "standard/server.py").read_bytes()


def test_plugin_validation_rejects_bad_manifests(families):
    folder = make_family(families)
    manifest = json.loads((folder / "family.json").read_text())
    for change, message in (
        ({"surprise": 1}, "unknown keys"),
        ({"hands": ["wuji", "sharpa"]}, "default 'sharpa'"),
        ({"action_dim": {"sharpa": 28}}, "action_dim"),
        ({"runtime": {"files": ["runtime.py"]}}, "replay.py"),
        ({"runtime": {"files": ["runtime.py", "replay.py", "../x.py"]}}, "relative"),
        ({"metadata": {"oracle": "partial"}}, "oracle_evidence"),
        ({"timeouts": {"agent_sec": 5400}}, "agent_sec"),
    ):
        (folder / "family.json").write_text(json.dumps({**manifest, **change}))
        with pytest.raises(ValueError, match=message):
            generate.load_plugin(folder)


def test_plugin_without_oracle_has_no_solution(families, tmp_path):
    make_family(families, oracle="none")
    out = tmp_path / "tasks"
    generate.render(out, {"fixture_plugin"})
    priv = out / "dexhand-fixture-plugin-i00-privileged"
    assert not (priv / "solution").exists()
    meta = tomllib.loads((priv / "task.toml").read_text())["metadata"]
    assert meta["oracle"] == "none" and meta["oracle_evidence"] == "fixture evidence"


def add_hand_solution(folder: Path, rows: int = 4, width: int = 26, hand: str = "wuji", task: str = "fixture_plugin",
                      directory: str = "wuji") -> None:
    (folder / "solution" / directory).mkdir(exist_ok=True)
    np.savez(folder / "solution" / directory / "trajectory.npz", actions=np.zeros((rows, width)), hand=np.array(hand),
             task=np.array(task))


def test_hand_solution_is_packaged_for_both_modes(families, tmp_path):
    folder = make_family(families)
    add_hand_solution(folder)
    out = tmp_path / "tasks"
    generate.render(out, {"fixture_plugin"})
    priv, std = out / "dexhand-fixture-plugin-i00-privileged", out / "dexhand-fixture-plugin-i00-standard"
    for task, mode, runner in ((priv, "privileged", "oracle.py"), (std, "standard", "oracle_replay.py")):
        solution = task / "solution"
        assert (solution / "wuji/trajectory.npz").read_bytes() == (folder / "solution/wuji/trajectory.npz").read_bytes()
        for name in (runner, "solution_parts.py"):   # unchanged copies of the shared runner next to the Wuji rows
            assert (solution / "wuji" / name).read_bytes() == (generate.SOLUTION / name).read_bytes()
            assert (solution / name).read_bytes() == (generate.SOLUTION / name).read_bytes()
        assert (solution / "trajectory.npz").is_file()   # the default (Sharpa Wave) rows stay where they were
        assert (solution / "solve.sh").read_bytes() == (generate.SOLUTION / f"solve_{mode}_by_hand.sh").read_bytes()
        assert (solution / "solve.sh").stat().st_mode & 0o111
        readme = (task / "README.md").read_text()
        reference = readme[readme.index("## Reference solution"):readme.index("## Verification")]
        assert "`solution/wuji/trajectory.npz`" in reference and "4 rows" in reference
        meta = tomllib.loads((task / "task.toml").read_text())["metadata"]
        assert "solution/wuji/trajectory.npz" in meta["oracle_evidence"] and "DEXHAND_HAND=wuji" in meta["oracle_evidence"]
        assert "solution/" not in (task / "instruction.md").read_text()   # nothing the agent reads locates it


def test_hand_solution_validation(families):
    folder = make_family(families)
    widths = {"sharpa": 28, "wuji": 26}
    default = folder / "solution/trajectory.npz"
    assert generate.hand_solutions(default, widths, "fixture_plugin") == {}
    for change, message in (
        ({"hand": "sharpa"}, "expected 'wuji'"),
        ({"width": 28}, "width 26"),
        ({"rows": 5}, "at most 4"),
        ({"task": "other_task"}, "task 'other_task'"),
    ):
        add_hand_solution(folder, **change)
        with pytest.raises(ValueError, match=message):
            generate.hand_solutions(default, widths, "fixture_plugin", max_rows=4)
    add_hand_solution(folder)
    assert generate.hand_solutions(default, widths, "fixture_plugin", 4) == {"wuji": folder / "solution/wuji/trajectory.npz"}
    with pytest.raises(ValueError, match="offered hand"):   # a family that does not offer Wuji
        generate.hand_solutions(default, {"sharpa": 28}, "fixture_plugin")
    add_hand_solution(folder, width=28, hand="sharpa", directory="sharpa")
    with pytest.raises(ValueError, match="offered hand"):   # the default hand's rows are solution/ itself
        generate.hand_solutions(default, widths, "fixture_plugin")


def test_release_subset_lists_ten_families():
    families = generate.release_families()
    assert len(families) == len(set(families)) == 10
    assert families[:6] == ["essential_cube_layer", "essential_held_joystick", "essential_pen_regrasp",
                            "essential_two_object", "essential_rotary_gait", "essential_cube_reorient"]


def test_compose_env_overrides_defaults_without_duplicate_keys():
    """A family's compose_env replaces a default key (duplicate keys make docker compose reject the file)."""
    text = generate.compose({"id": "fixture"}, {"compose_env": {"RCB_STARTUP_TIMEOUT_S": "600", "EXTRA_FLAG": 1}})
    keys = [line.split(":", 1)[0].strip() for line in text.split("environment:\n", 1)[1].splitlines() if line.strip()]
    assert len(keys) == len(set(keys)), keys
    assert 'RCB_STARTUP_TIMEOUT_S: "600"' in text and 'RCB_STARTUP_TIMEOUT_S: "300"' not in text
    assert 'EXTRA_FLAG: "1"' in text and "DEXHAND_HAND: ${DEXHAND_HAND:-sharpa}" in text
    with pytest.raises(ValueError):
        generate.compose({"id": "fixture"}, {"compose_env": {"DEXHAND_HAND": "wuji"}})


def test_compose_env_override_parses_as_yaml():
    yaml = pytest.importorskip("yaml")
    text = generate.compose({"id": "fixture"}, {"compose_env": {"RCB_STARTUP_TIMEOUT_S": "600"}})
    assert yaml.safe_load(text)["services"]["sim"]["environment"]["RCB_STARTUP_TIMEOUT_S"] == "600"
