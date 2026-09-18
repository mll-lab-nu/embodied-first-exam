"""Execute a half-step recheck from the baseline's frozen Python modules.

Long running variants may overlap subsequent development. This changes module
loading only; robot motors, contacts and acceptance use the recorded sources.
"""
import hashlib
import importlib
import json
from pathlib import Path
import runpy
import sys


def maybe_run_snapshot(module, caller_file):
    if "--output" not in sys.argv:
        return
    output=Path(sys.argv[sys.argv.index("--output")+1]).resolve()
    if output.name != "half_step":
        return
    source=output.parent/"baseline/source"
    if Path(caller_file).resolve().parent == source:
        return
    if not (source/f"{module}.py").is_file():
        raise RuntimeError(f"Missing baseline source snapshot for recheck: {source}")
    package_name="topogym.tasks.fiber_bundling"
    package=importlib.import_module(package_name)
    fallback=[p for p in package.__path__ if Path(p).resolve()!=source]
    package.__path__=[str(source),*fallback]
    for name in list(sys.modules):
        if name.startswith(package_name+"."):
            del sys.modules[name]
    try:
        runpy.run_module(f"{package_name}.{module}",run_name="__main__",alter_sys=True)
    finally:
        if output.exists():
            (output/"snapshot_execution.json").write_text(json.dumps(dict(
                source_directory=str(source),module=module,
                purpose="same physical controller sources as baseline; independent reset and live simulation",
                source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob("*.py")}),indent=2)+"\n")
            (output/"execution_bootstrap.py").write_bytes(Path(__file__).read_bytes())
    raise SystemExit(0)
