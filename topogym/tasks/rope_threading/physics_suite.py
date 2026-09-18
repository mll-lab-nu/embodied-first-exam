"""Run serial GPU probes, preserving failures and gating full recording."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from .physics_review import build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--wait-for", help="An already running case directory; do not start a second GPU job")
    parser.add_argument("--reference-speed", type=float, default=4.)
    parser.add_argument("--record-to", type=Path)
    args = parser.parse_args()
    root = args.folder.resolve()
    root.mkdir(parents=True, exist_ok=True)
    mapping_path = root/"cases.json"
    mapping = json.loads(mapping_path.read_text()) if mapping_path.exists() else {}
    cases = [("free_baseline", []), ("ring_contact", ["--mode", "ring_contact"]),
        ("free_halfdt", ["--dt", ".0025"]),
        ("ring_halfdt", ["--mode", "ring_contact", "--dt", ".0025"]),
        ("ring_refined", ["--mode", "ring_contact", "--refined"]),
        ("robot_prefix", ["--mode", "reference_prefix", "--reference-speed", str(args.reference_speed)])]
    if args.wait_for:
        waiting = root/args.wait_for
        start = time.monotonic()
        while not (waiting/"report.json").exists():
            if (root/"STOP_SUITE").exists() or time.monotonic()-start > 7200:
                raise SystemExit("Stopped while waiting; no new GPU job launched")
            time.sleep(5)
    for name, flags in cases:
        if (root/"STOP_SUITE").exists():
            raise SystemExit("Explicit suite stop; remaining cases are incomplete")
        case_root = root/mapping.get(name, name)
        report_path = case_root/"report.json"
        if report_path.exists():
            prior = json.loads(report_path.read_text())
            if prior.get("passed"):
                print(f"{name}: retained completed evidence", flush=True)
                continue
            if prior.get("failure_category") != "runtime_initialization":
                build(root)
                raise SystemExit(f"{name}: physical gate failed; inspect before changing or rerunning")
            attempt = 2
            while (root/f"{name}_attempt_{attempt}").exists():
                attempt += 1
            mapping[name] = f"{name}_attempt_{attempt}"
            mapping_path.write_text(json.dumps(mapping, indent=2)+"\n")
            case_root = root/mapping[name]
        elif (case_root/"validation_spec.json").exists():
            raise SystemExit(f"{name}: incomplete evidence exists; inspect it before rerunning")
        case_root.mkdir(parents=True, exist_ok=True)
        print(f"{name}: starting {case_root}", flush=True)
        command = [sys.executable, "-m", "topogym.tasks.rope_threading.physics_probe", "--output", str(case_root), *flags]
        with (case_root/"process.log").open("w") as log:
            completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        result = build(root)
        if completed.returncode or not json.loads((case_root/"report.json").read_text()).get("passed"):
            raise SystemExit(f"{name}: failed (exit {completed.returncode}); full recording remains disabled")
        rejected = [name for name, comparison in result["comparisons"].items()
                    if "comparison_samples" in comparison and not comparison["passed"]]
        if rejected:
            raise SystemExit(f"Numerical comparisons failed: {rejected}; inspect before further probes or recording")
    result = build(root)
    if not result["passed"]:
        raise SystemExit("Numerical comparisons failed; full recording remains disabled")
    if args.record_to:
        if args.record_to.exists() and any(args.record_to.iterdir()):
            raise FileExistsError("Recording destination must be new; existing evidence is preserved")
        args.record_to.mkdir(parents=True, exist_ok=True)
        command = [sys.executable, "-m", "topogym.tasks.rope_threading.physics_probe", "--mode", "full_threading",
            "--output", str(args.record_to), "--qualification", str(root/"qualification.json"),
            "--reference-speed", str(args.reference_speed), "--record"]
        with (args.record_to/"process.log").open("w") as log:
            completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        if completed.returncode:
            raise SystemExit("Full physical recording did not complete successfully; inspect its report")


if __name__ == "__main__":
    main()
