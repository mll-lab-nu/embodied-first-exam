"""Run serial GPU probes, preserving failures and gating full recording."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import time

from .physics_review import build


def wait_for_gpu_memory(root, required_mib):
    """Avoid repeating the observed OOM when another task occupies the GPU."""
    announced = False
    while True:
        if (root/"STOP_SUITE").exists():
            raise SystemExit("Stopped while waiting for GPU memory")
        free = int(subprocess.check_output([
            "nvidia-smi", "--id=0", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            text=True, timeout=10).strip().splitlines()[0])
        if free >= required_mib:
            return
        if not announced:
            print(f"Waiting for GPU memory: {free} MiB free; {required_mib} MiB required. Other jobs remain running.", flush=True)
            announced = True
        time.sleep(5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--config-name", default="rope_threading_preview")
    parser.add_argument("--wait-for", help="An already running case directory; do not start a second GPU job")
    parser.add_argument("--reference-speed", type=float, default=4.)
    parser.add_argument("--ring-halfdt-seconds", type=float,
                        help="Optional longer observation of the unchanged half-timestep loading protocol")
    parser.add_argument("--record-to", type=Path)
    parser.add_argument("--record-config-name", help="Recording configuration; physical equivalence is enforced")
    args = parser.parse_args()
    root = args.folder.resolve()
    root.mkdir(parents=True, exist_ok=True)
    mapping_path = root/"cases.json"
    mapping = json.loads(mapping_path.read_text()) if mapping_path.exists() else {}
    cases = [("ring_contact", ["--mode", "ring_contact"]),
        ("ring_halfdt", ["--mode", "ring_contact", "--dt", ".0025"]),
        ("ring_refined", ["--mode", "ring_contact", "--refined"]),
        ("free_baseline", []), ("free_halfdt", ["--dt", ".0025"]),
        ("robot_prefix", ["--mode", "reference_prefix", "--reference-speed", str(args.reference_speed)])]
    if args.ring_halfdt_seconds is not None:
        if not math.isfinite(args.ring_halfdt_seconds) or args.ring_halfdt_seconds <= 0:
            parser.error('ring-halfdt-seconds must be finite and positive')
        cases[1][1].extend(['--seconds', str(args.ring_halfdt_seconds)])
    if args.wait_for:
        waiting = root/args.wait_for
        start = time.monotonic()
        while True:
            alive = False
            if (waiting/"process_info.json").exists():
                info = json.loads((waiting/"process_info.json").read_text())
                try:
                    alive = Path(f'/proc/{info["pid"]}/stat').read_text().split()[21] == info["start_ticks"]
                except FileNotFoundError:
                    pass
            if (waiting/"report.json").exists() and not alive:
                break
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
        # The isolated ring probe actually used about 6.9 GiB. Leave room
        # for initialization and refinement, and more for articulated bodies.
        wait_for_gpu_memory(root, 10240 if name.startswith("ring_") else 12288)
        print(f"{name}: starting {case_root}", flush=True)
        command = [sys.executable, "-m", "topogym.tasks.rope_threading.physics_probe", "--output", str(case_root),
                   "--config-name", args.config_name, *flags]
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
        wait_for_gpu_memory(root, 14336)
        record_config = args.record_config_name
        request = root/'recording_request.json'
        if record_config is None and request.is_file():
            plan = json.loads(request.read_text())
            if Path(plan['output_directory']).resolve() != args.record_to.resolve():
                raise ValueError('Saved recording request names a different destination')
            record_config = plan['config_name']
        command = [sys.executable, "-m", "topogym.tasks.rope_threading.physics_probe", "--mode", "full_threading",
            "--output", str(args.record_to), "--qualification", str(root/"qualification.json"),
            "--config-name", record_config or args.config_name,
            "--reference-speed", str(args.reference_speed), "--record"]
        with (args.record_to/"process.log").open("w") as log:
            completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        if completed.returncode:
            raise SystemExit("Full physical recording did not complete successfully; inspect its report")


if __name__ == "__main__":
    main()
