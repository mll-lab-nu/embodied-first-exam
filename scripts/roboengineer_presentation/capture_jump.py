"""Capture a verified ramp-jump replay from an explicit frozen operator source tree."""

import argparse
import json
from pathlib import Path
import sys

from scripts.roboengineer_presentation.capture import Capture, export, sha


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-root", type=Path, required=True)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--index", type=int, default=0)
    p.add_argument("--case", type=int, default=0)
    p.add_argument("--showcase-config", type=Path)
    p.add_argument("--reference-dir", type=Path)
    a = p.parse_args()
    a.source_root = a.source_root.resolve()
    # Use only the supplied task source, while retaining this operator capture tool.
    # This allows a prototype to be rendered without registering it as a benchmark.
    assert not any(k.startswith("scripts.control_transfer") for k in sys.modules)
    import scripts

    scripts.__path__ = [str(a.source_root / "scripts")]
    from scripts.control_transfer.trusted import anycar_jump

    assert Path(anycar_jump.__file__).is_relative_to(a.source_root)
    custom = None
    if a.showcase_config:
        if not a.reference_dir:
            p.error("--showcase-config requires --reference-dir")
        custom = json.loads(a.showcase_config.read_text())
        source = a.reference_dir / "record.json"
    else:
        spec = json.loads((a.evidence / f"instance{a.index}.json").read_text())
        case = spec["bank"]["held_out"][a.case]
        source = a.evidence / f"instance{a.index}/held_out/{a.case}/record.json"
    original = json.loads(source.read_text())
    assert original["metrics"]["success"], (
        "This presentation requires a successful reference"
    )
    a.out.mkdir(parents=True, exist_ok=True)
    with Capture() as capture:
        if custom:
            policy = custom["policy"]
            replay = anycar_jump.run(
                policy,
                anycar_jump.validate(policy),
                custom["course"],
                anycar_jump.plant_parameters(custom["plant_seed"]),
                custom["friction"],
                custom["initial_y"],
                custom["initial_yaw"],
                custom["noise_seed"],
                a.out / "verified-replay",
                False,
            )
        else:
            replay = anycar_jump.rollout(
                a.evidence / "policy.json", case, a.out / "verified-replay", False
            )
    for key in ("state_sha256", "policy_sha256", "metrics", "feedback", "dynamics"):
        assert replay[key] == original[key], f"Archived replay mismatch: {key}"
    course = replay["feedback"]["command"]
    export(
        "anycar-jump",
        capture.model,
        capture.frames,
        original,
        source,
        a.out / "captures",
        dict(
            title="AnyCar Ramp Jump",
            subtitle="Wide-gap showcase · fast approach and controlled stop"
            if custom
            else "Clear the gap, land on the ramp, stop on the runout",
            status="Custom showcase: success"
            if custom
            else "Scripted reference case: success",
            note=f"{course['gap']:.2f} m gap · "
            + (
                "new simulated demo configuration"
                if custom
                else "exact rigid-body contact replay"
            )
            + " · no coding-agent run",
            ground_z=-1.2,
            course=course,
            showcase_revision=custom["revision"] if custom else None,
            benchmark_case=not bool(custom),
            poster_time_s=(
                original["metrics"]["takeoff_s"] + original["metrics"]["touchdown_s"]
            )
            / 2,
        ),
    )
    sources = {
        str(Path(m.__file__).relative_to(a.source_root)): sha(m.__file__)
        for key, m in sys.modules.items()
        if key.startswith("scripts.control_transfer") and getattr(m, "__file__", None)
    }
    (a.out / "capture-audit.json").write_text(
        json.dumps(
            dict(
                source_record_sha256=sha(source),
                state_sha256=replay["state_sha256"],
                exact_metrics=True,
                exact_feedback=True,
                exact_dynamics=True,
                showcase_config_sha256=sha(a.showcase_config) if custom else None,
                benchmark_case=not bool(custom),
                frames=len(capture.frames),
                source_files=sources,
                presentation_only=True,
                agent_feedback=False,
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
