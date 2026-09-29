"""Check active import/clock boundaries, rather than obsolete directory counts."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def active_sources():
    return [p for p in (ROOT / "topogym").rglob("*.py")
            if "deferred" not in p.parts and not p.is_relative_to(ROOT / "topogym/tasks/legacy")]


def test_no_direct_second_engine_or_retired_imports():
    forbidden = (
        "mujoco",
        "topogym.redundants",
        "topogym.tasks.legacy",
        "topogym.agent_bridge",
        "topogym.generation",
        "topogym.envs",
        "topogym.policies",
        "topogym.assets.generators",
        "topogym.assets.variants",
        "topogym.assets.appearance",
        "topogym.world.nyx_lab",
        "topogym.world.lab_layout",
    )
    problems = []
    for path in active_sources():
        for node in ast.walk(ast.parse(path.read_text())):
            names = (
                [item.name for item in node.names]
                if isinstance(node, ast.Import)
                else ([node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            )
            for name in names:
                if any(
                    name == prefix or name.startswith(prefix + ".")
                    for prefix in forbidden
                ):
                    problems.append((str(path.relative_to(ROOT)), node.lineno, name))
    assert problems == []
    assert not (ROOT / "topogym/redundants").exists()


def test_world_is_only_scene_step_owner():
    offenders = []
    for path in active_sources():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "step"
            ):
                owner = ast.unparse(node.func.value)
                if owner.endswith("scene") and path.name != "genesis_world.py":
                    offenders.append((path, node.lineno))
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
                if any(
                    isinstance(t, ast.Attribute) and t.attr == "step" for t in targets
                ):
                    offenders.append((path, node.lineno))
    assert offenders == []


def test_tasks_do_not_own_engine_or_output():
    for path in (ROOT / "topogym/tasks").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            modules = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else ([node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            )
            assert not any(
                m == "genesis"
                or m.startswith(
                    ("topogym.recording", "topogym.agents", "topogym.robot")
                )
                for m in modules
            ), (path, node.lineno)


def test_task_names_are_files_in_functional_modules():
    from topogym.config.registry import task_catalog, variation_catalog
    task_names = {row["task_id"] for row in task_catalog()}
    for module in ("assets", "solvers", "world", "sensors", "evaluation", "planning"):
        assert not [
            p
            for p in (ROOT / "topogym" / module).rglob("*")
            if p.is_dir() and p.name in task_names and "resources" not in p.parts
        ], module
    assert {p.name for p in (ROOT / "topogym/tasks").iterdir() if p.is_dir()} <= task_names | {
        "task_variations",
        "legacy",
        "__pycache__",
    }
    for name in task_names:
        assert not (ROOT / "topogym/tasks" / f"{name}.py").exists()
        for tier in ("easy", "medium", "hard"):
            assert (ROOT / "topogym/tasks" / name / f"{name}_{tier}.py").is_file()
        rows = variation_catalog(name)
        assert all(not row["implementation"].startswith("topogym.tasks.legacy.") for row in rows)
        if all(row["status"] == "integrated" for row in rows if row["pool"] == "tier"):
            assert {p.name for p in (ROOT / "topogym/tasks" / name).glob("*.py")} == {
                "__init__.py", "common.py", *(f"{name}_{tier}.py" for tier in ("easy", "medium", "hard"))}
    assert (ROOT / "topogym/simulator/env.py").is_file() and (
        ROOT / "topogym/simulator/history.py"
    ).is_file()
    assert not (ROOT / "topogym/envs").exists()
