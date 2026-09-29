"""Install a real wheel outside the checkout and exercise its public runtime."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import venv
import pytest

pytestmark = [pytest.mark.genesis, pytest.mark.render]


def test_installed_runtime(tmp_path):
    root = Path(__file__).resolve().parents[2]
    output = Path(os.environ["TOPOGYM_TEST_OUTPUT"])
    build = tmp_path / "source"
    build.mkdir()
    shutil.copy2(root / "pyproject.toml", build)
    shutil.copytree(root / "topogym", build / "topogym", ignore=shutil.ignore_patterns("__pycache__", "agents"))
    # Invoke the declared build backend directly: uv-managed runtime venvs need
    # not contain pip. Source/output stay temporary; install pip lives only in
    # the fresh validation venv below.
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    subprocess.run([sys.executable, "-c",
                    "import sys; from setuptools.build_meta import build_wheel; build_wheel(sys.argv[1])",
                    str(wheels)], cwd=build, check=True)
    # Reuse pinned engine libraries; TopoGym itself is a regular wheel install.
    destination = tmp_path / "installed"
    venv.EnvBuilder(with_pip=True).create(destination)
    # Offline dependency reuse, not an editable TopoGym install or source path.
    site_dir = destination / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
    (site_dir / "pinned_engine_dependencies.pth").write_text(sysconfig.get_path("purelib") + "\n")
    python = str(destination / "bin/python")
    wheel, = (tmp_path / "wheels").glob("topogym*.whl")
    subprocess.run([python, "-m", "pip", "install", "--no-deps", "--ignore-installed", str(wheel)], check=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    shutil.copy2(root / "tests/runtime_evidence.py", outside)
    script = outside / "check.py"
    script.write_text('''from pathlib import Path
import os, sys, traceback
import topogym
from runtime_evidence import RuntimeEvidence
assert Path(topogym.__file__).resolve().is_relative_to(Path(sys.prefix))
assert len(topogym.env_list()) == 13
cfg = topogym.SimulatorConfig(enable_privileged=True)
evidence = RuntimeEvidence(Path(os.environ["TOPOGYM_TEST_OUTPUT"]) / "installation", "installation", cfg)
error = None
try:
    with topogym.make("cast_coil", enable_privileged=True) as env:
        with evidence.stage("non_editable_wheel_outside_checkout") as stage:
            stage["import_path"] = topogym.__file__
            obs, info = env.reset(seed=19)
            evidence.sample(env, obs, info, label="initial")
            actor = env.interaction(privileged=True)
            assert not hasattr(actor, "reset")
            for _ in range(3):
                obs, _, done, truncated, info = actor.step({})
                assert not done and not truncated
                evidence.sample(env, obs, info, action={})
            actor.render()
            evidence.end_recording()
except BaseException:
    error = traceback.format_exc()
    raise
finally:
    evidence.close(error)
''')
    environment = dict(os.environ, TOPOGYM_ASSET_ROOT=str(root / "assets"))
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    subprocess.run([python, str(script)], cwd=outside, env=environment, check=True)
