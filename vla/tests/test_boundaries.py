"""Process boundaries: model code never imports topogym; Gym code never imports model libraries."""
import ast
from pathlib import Path

VLA = Path(__file__).resolve().parents[1]
MODEL_LIBRARIES = {"torch", "jax", "transformers", "openpi", "gr00t"}


def imported_roots(path):
    roots = set()
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            roots |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def offenders(paths, forbidden):
    found = {str(path.relative_to(VLA)): sorted(imported_roots(path) & forbidden) for path in paths}
    return {name: roots for name, roots in found.items() if roots}


def test_shared_and_model_code_do_not_import_topogym():
    assert offenders([VLA / "protocol.py", VLA / "config.py", *(VLA / "models").rglob("*.py")], {"topogym"}) == {}


def test_gym_does_not_import_model_libraries():
    assert offenders((VLA / "gym").rglob("*.py"), MODEL_LIBRARIES) == {}
