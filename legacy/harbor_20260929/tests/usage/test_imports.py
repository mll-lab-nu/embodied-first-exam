import subprocess
import sys


def test_core_import_has_no_simulator_or_provider_sdk_dependency():
    result = subprocess.run([sys.executable, "-c", "import sys; import topogym.agents.usage; "
        "assert not any(x in sys.modules for x in ['numpy','scipy','genesis','harbor','openai','anthropic'])"],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_core_import_does_not_load_harbor_runner():
    result = subprocess.run([sys.executable, '-c',
        "import sys; from topogym.agents.usage import UsagePipeline; "
        "assert not any(x.startswith('harbor_runners') for x in sys.modules)"],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
