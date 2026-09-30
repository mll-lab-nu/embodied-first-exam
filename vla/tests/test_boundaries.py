"""Process boundaries: the protocol needs only the standard library and NumPy, model code never imports topogym
or the Gym side, and Gym code never imports model libraries."""
import ast
from pathlib import Path

VLA = Path(__file__).resolve().parents[1]
MODEL_LIBRARIES = {"torch", "jax", "transformers", "openpi", "gr00t"}


def imported_modules(path):
    modules = set()
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            modules |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            modules.add(node.module)
    return modules


def offenders(paths, forbidden):
    """Imported modules that are, or lie inside, a forbidden module, per file."""
    found = {str(path.relative_to(VLA)): sorted(module for module in imported_modules(path)
                                                  if any(module == name or module.startswith(name + ".")
                                                         for name in forbidden))
             for path in paths}
    return {name: modules for name, modules in found.items() if modules}


def test_the_protocol_needs_only_the_standard_library_and_numpy():
    assert imported_modules(VLA / "protocol.py") <= {"__future__", "dataclasses", "json", "math", "struct", "numpy"}


def test_shared_and_model_code_import_neither_topogym_nor_the_gym_side():
    paths = [VLA / "protocol.py", VLA / "config.py", *(VLA / "models").rglob("*.py")]
    assert offenders(paths, {"topogym", "vla.gym"}) == {}


def test_gym_does_not_import_model_libraries():
    assert offenders((VLA / "gym").rglob("*.py"), MODEL_LIBRARIES) == {}
