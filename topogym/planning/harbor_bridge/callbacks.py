"""Shared setup for task callbacks; the caller owns the simulator and recorder."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from .actions import SessionPolicyRunner


def fingerprint(value):
    """Same numerical record hash without the development-only SegmentRunner."""
    from topogym.utils.io import to_jsonable
    from .contracts import json_digest
    return json_digest(to_jsonable(value))


def prepare_output(session, output, module_file):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "private").mkdir(exist_ok=True)
    source = Path(module_file)
    manifest = dict(callback_file=source.name, callback_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    runtime_binding=session.runtime_binding, instance_sha=session.instance_sha,
                    scope="Harbor-owned Session; independent grading required")
    for name in ("source_manifest.json", "run_source_manifest.json"):
        (output / name).write_text(json.dumps(manifest, indent=2) + "\n")
    return output


def run_stages(session, output, factory, *, selection=None, runner=None):
    from topogym.planning.solvability import QualificationWorkflow, PathCache, identity_for
    output = prepare_output(session, output, __file__)
    runner = SessionPolicyRunner(session) if runner is None else runner   # e.g. standard_rate.rate_limited_runner
    runner.root = output
    identity = identity_for(runner)
    flow = QualificationWorkflow(runner, output / "qualification", identity, mode="session")
    context = SimpleNamespace(output=output, identity=identity, cache=PathCache(output / "path_cache", identity))
    for index, step in enumerate(factory(session.env, context)):
        candidates = None
        if selection is not None:
            if index >= len(selection) or selection[index]["step"] != step.name:
                raise ValueError(f"Selected recipe differs at step {index}: {step.name}")
            candidates = [selection[index]["parameters"]]
        flow.run_step(step, candidates)
        if session.success():
            break
    return flow.finish()


def data_path(relative):
    """References are copied into the private solution and hashed by its manifest."""
    base = Path(__file__).parent / "reference_data"
    path = (base / relative).resolve()
    if not path.is_relative_to(base.resolve()) or not path.is_file():
        raise ValueError(f"Missing private reference data: {relative}")
    return path
