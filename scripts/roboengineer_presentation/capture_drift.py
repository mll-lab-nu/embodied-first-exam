"""Export the verified nominal tight-bay demonstration, keeping its limitations."""

import argparse
import json
from pathlib import Path

from scripts.roboengineer_presentation.capture import Capture, export, sha
from scripts.control_transfer.trusted.anycar_drift_v3 import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    source = args.evidence / "nominal/first/record.json"
    original = json.loads(source.read_text())
    policy = json.loads((args.evidence / "policy.json").read_text())
    course = original["feedback"]["command"]
    dynamics = original["dynamics"]
    with Capture() as capture:
        replay = run(
            policy,
            course,
            dynamics["plant"],
            dynamics["friction"],
            dynamics["brake_torque"],
            args.out / "verified-replay",
        )
    assert replay == original, "Nominal whole-record replay mismatch"
    assert replay["metrics"]["success"]
    export(
        "anycar-drift-v3",
        capture.model,
        capture.frames,
        original,
        source,
        args.out / "captures",
        dict(
            title="Tight Drift Parking",
            subtitle="180-degree drift into a 0.69 x 0.43 m bay",
            status="Nominal success only",
            note="Nominal score 64.70 · held-out 1/20 · adaptation 0/6 · additional noise 1/10",
            poster_time_s=8.4,
            reference_scope="Selected nominal positive; brittle frozen reference, no coding-agent or Harbor run",
        ),
    )
    (args.out / "capture-audit.json").write_text(
        json.dumps(
            dict(
                source_record_sha256=sha(source),
                state_sha256=replay["state_sha256"],
                whole_record_exact=True,
                frames=len(capture.frames),
                nominal_only=True,
                agent_run=False,
                native_harbor=False,
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
