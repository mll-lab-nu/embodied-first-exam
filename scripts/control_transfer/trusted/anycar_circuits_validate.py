"""Operator-only all-venue smoke campaign, not a full multi-round benchmark score."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
from ..components.anycarbench.tracks import catalog, get_route
from ..control_public.anycar import DEFAULT, validate
from .anycar_reference import public_feedback


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    sources = [
        *root.glob("anycar*.py"),
        *root.glob("trusted/anycar*.py"),
        *root.glob("control_public/anycar*.py"),
        *root.glob("components/anycarbench/*"),
    ]
    frozen = {str(f.relative_to(root)): hashlib.sha256(f.read_bytes()).hexdigest() for f in sources if f.is_file()}
    write(a.out / "source-sha256.json", frozen)
    policy = a.out / "nominal-policy.json"
    policy.write_bytes(validate(DEFAULT))
    circuits = sorted({v["circuit_id"] for v in catalog()["circuits"].values()})
    outcomes = []

    def run(name, index, render=False, label=None):
        route = get_route(name)
        # Cover a bend rather than only a long start/finish straight. Public geometry only.
        distances = np.linspace(0, route.length, 4096, endpoint=False)
        peak = distances[np.argmax(np.abs(route.at(distances)[:, 3]))]
        start = float(((peak - 8) % route.length) / route.length)
        case = dict(
            track_id=route.name,
            plant_seed=10100 if index % 2 == 0 else 11100,
            episode_seed=10300 + index,
            start_fraction=start,
        )
        folder = a.out / (label or name)
        cmd = [
            sys.executable,
            "-m",
            "scripts.control_transfer.trusted.anycar",
            "--policy",
            str(policy),
            "--out",
            str(folder),
            "--plant-seed",
            str(case["plant_seed"]),
            "--episode-seed",
            str(case["episode_seed"]),
            "--track",
            route.name,
            "--start-fraction",
            str(start),
        ]
        if not render:
            cmd.append("--no-render")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode:
            raise RuntimeError(result.stderr)
        record = json.loads((folder / "record.json").read_text())
        if render:
            subprocess.run(
                ["ffmpeg", "-v", "error", "-threads", "1", "-i", str(folder / "video.mp4"), "-f", "null", "-"],
                capture_output=True,
                check=True,
                timeout=60,
            )
            public = public_feedback(record, folder)
            # Large circuits must not push the fixed close-up behind a scene-scaled near plane.
            raw = subprocess.check_output(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-threads",
                    "1",
                    "-i",
                    str(folder / "video.mp4"),
                    "-vf",
                    "select=eq(n\\,70)",
                    "-frames:v",
                    "1",
                    "-f",
                    "rawvideo",
                    "-pix_fmt",
                    "rgb24",
                    "-",
                ],
                timeout=60,
            )
            frame = np.frombuffer(raw, dtype=np.uint8).reshape(480, 1280, 3)
            for panel in (frame[:, :640], frame[:, 640:]):
                if float(panel.mean()) < 5 or float(panel.std()) < 5:
                    raise ValueError("Clipped or blank diagnostic video panel")
            write(folder / "delivered-feedback.json", public)
        return dict(
            name=name,
            case=case,
            length_m=route.length,
            scale=route.scale,
            metrics=record["metrics"],
            state_sha256=record["state_sha256"],
        )

    for i, name in enumerate(["zigzag", *circuits]):
        result = run(name, i)
        outcomes.append(result)
        write(a.out / "progress.json", outcomes)
        print(json.dumps(result), flush=True)
    examples = []
    for name in ["zigzag", "suzuka", "monaco", "silverstone"]:
        index = ["zigzag", *circuits].index(name)
        result = run(name, index, True, label=name + "-video")
        assert (
            result["state_sha256"] == outcomes[index]["state_sha256"]
            and result["metrics"] == outcomes[index]["metrics"]
        )
        examples.append(result)
    assert all(hashlib.sha256((root / name).read_bytes()).hexdigest() == sha for name, sha in frozen.items())
    write(
        a.out / "validation.json",
        dict(
            schema="anycar-all-venue-smoke/1",
            source_sha256=frozen,
            venues=78,
            layouts_available=159,
            sector_seconds=24,
            full_laps_tested=False,
            adaptation_tested=False,
            outcomes=outcomes,
            video_exact_replays=examples,
            successes=sum(x["metrics"]["success"] for x in outcomes),
        ),
    )


if __name__ == "__main__":
    main()
