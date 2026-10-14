"""Isolated packaging settings for the unaccepted multi-round policy proposal.

Reuse main's formatter without changing its imported module or global registry.
These settings are experimental and never waive the authoritative protocol.
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROPOSAL_ROOT = ROOT / "experimental/roboengineer"
TASK_ROOT = PROPOSAL_ROOT / "tasks"

_spec = importlib.util.spec_from_file_location(
    "_roboengineer_proposal_conventions", ROOT / "scripts/task_conventions.py"
)
_conventions = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_conventions)
_conventions.BENCHMARKS = [("quadrotor-landing-", "Neural Lander"), ("control-transfer-", "Control Transfer")]
_conventions.NO_TWIN = {
    prefix: "— (experimental multi-round policy proposal; not an accepted standard-mode task)"
    for prefix, _ in _conventions.BENCHMARKS
}
_conventions.CUTOFFS_FILE = PROPOSAL_ROOT / "cutoffs.toml"
_conventions.RESOURCES_FILE = PROPOSAL_ROOT / "resources.toml"
# Retains the historical long-lap experiment only. This is not main's cap table.
_conventions.CUTOFF_CAP_EXCEPTIONS = {"Control Transfer": 129600}
cutoff_sec = _conventions.cutoff_sec
cutoff_overrides = _conventions.cutoff_overrides


def require_experimental_destination(path):
    """Never let a proposal generator populate the accepted task registry."""
    path = Path(path).resolve()
    if path.is_relative_to((ROOT / "tasks").resolve()):
        raise ValueError("Experimental policy packages cannot be written under the accepted tasks/ registry")


def normalize(task):
    task = Path(task)
    require_experimental_destination(task)
    toml = task / "task.toml"
    contents = toml.read_text()
    if 'proposal = "roboengineer-policy-adaptation"' not in contents:
        contents = contents.replace(
            "[metadata]\n",
            '[metadata]\nexperimental = true\nproposal = "roboengineer-policy-adaptation"\n',
            1,
        )
        toml.write_text(contents)
    _conventions.normalize(task)
    readme = task / "README.md"
    title, _, body = readme.read_text().partition("\n")
    notice = (
        "\n> Experimental multi-round policy proposal. This package is not admitted by main's "
        "`eai-standard/2.x` protocol or listed in the accepted dataset. Its historical ID is retained "
        "for traceability; successful package checks are not protocol approval.\n"
    )
    readme.write_text(title + "\n" + notice + body)
