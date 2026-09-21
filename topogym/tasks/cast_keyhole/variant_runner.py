"""EpisodeRunner adapter: actual joint-control validation, never a dataset export."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
from pathlib import Path
import shutil

from topogym.generation.episode_spec import (EpisodeArtifact, EpisodeKey, EpisodeResult,
    EpisodeSpec, ExecutionProfile, ScenePreset, TaskLayout, TaskVariant)
from topogym.runtime.episode_runner import EpisodeRunContext
from .variants import _new_output, check_spec, file_sha, prepare, save


def load_spec(path):
    d = json.loads(Path(path).read_text())
    key = EpisodeKey(**d["key"])
    variant = dict(d["variant"])
    variant["key"] = EpisodeKey(**variant["key"])
    return EpisodeSpec(key, ScenePreset(**d["preset"]), TaskVariant(**variant),
        TaskLayout(**d["layout"]) if d["layout"] else None,
        ExecutionProfile(**d["execution_profile"]), d["resolved_config"])


class KeyholeVariantRunner:
    def __init__(self, output, *, workers=2):
        self.output = Path(output)
        self.workers = min(2, max(1, int(workers)))

    def run(self, context: EpisodeRunContext) -> EpisodeResult:
        spec = context.spec
        output = _new_output(self.output)
        try:
            check_spec(spec)
            if context.plan is not None or context.options.viewer or context.options.record_video is not None:
                raise ValueError("This validation runner consumes its checked family motion; viewer/recording use physical_recording separately")
            if spec.execution_profile.speed_scale != 1. or spec.execution_profile.profile_id != "keyhole_contact_assisted_dual_arm_v2":
                raise ValueError("Unsupported execution profile")
            if spec.layout is None:
                spec, folder = prepare(spec, output / "prepared")
            else:
                meta = spec.layout.metadata
                source = Path(meta["geometry_path"]).parent
                if Path(meta["motion_path"]).parent != source:
                    raise ValueError("Geometry and motion must share one certified directory")
                for name, key in (("geometry.json", "geometry_sha256"), ("robot_motion.json", "motion_sha256"),
                                  ("certificate.json", "certificate_sha256")):
                    if file_sha(source / name) != meta[key]:
                        raise ValueError(f"Prepared input changed: {name}")
                folder = output / "instance"
                folder.mkdir()
                for name in ("geometry.json", "robot_motion.json", "certificate.json", "ik_proposal.json", "proposal.json"):
                    shutil.copy2(source / name, folder / name)
            from .family_pipeline import audit, physics, qualify_physics
            from .variant_assets import require_variant
            require_variant(folder / "geometry.json", json.loads((folder / "robot_motion.json").read_text()))
            save(output / "episode_spec.json", asdict(spec))
            # Subprocess isolation keeps Genesis state and timestep configuration
            # independent between episodes and the two verification runs.
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                futures = [pool.submit(physics, folder, half) for half in (False, True)]
                for future in futures:
                    future.result()
            for half in (False, True):
                audit(folder, half)
            proof = qualify_physics(folder)
            result = EpisodeResult.ok(spec.key, export_ready=False,
                metrics=dict(two_timesteps_verified=True, pregrasp_start=True, assisted_weld_grasp=True,
                    held_at_end=True, dataset_export_performed=False,
                    min_gap_m=min(v["minimum_gap_m"] for v in proof["physics"].values())),
                artifacts=(EpisodeArtifact("qualification", str(folder / "qualification.json")),
                           EpisodeArtifact("physical_trajectory", str(folder / "robot_physics/trajectory.json")),
                           EpisodeArtifact("physical_trajectory_half_dt", str(folder / "robot_physics_half/trajectory.json"))))
        except Exception as error:
            result = EpisodeResult.failed(spec.key, f"{type(error).__name__}: {error}")
        save(output / "episode_result.json", asdict(result))
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    result = KeyholeVariantRunner(args.output, workers=args.workers).run(EpisodeRunContext(load_spec(args.spec)))
    print(json.dumps(asdict(result), indent=2, default=str))
    if not result.success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
