"""Same-camera, real-time comparison of the three measured approach segments.

This is explicitly a partial comparison, not three full robot demos. The input
runs must independently complete the physical task before comparison is allowed.
"""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path

import numpy as np
from omegaconf import OmegaConf

from .variant_generator import file_hash
from .variant_pipeline import qualify


def render(folders, output):
    import genesis as gs
    import imageio.v2 as imageio
    from PIL import Image
    from .scene import build_scene
    folders = [Path(p).resolve() for p in folders]
    output = Path(output).resolve()
    prepared, proofs, inputs = [], [], []
    for index, folder in enumerate(folders, 1):
        proof = qualify(folder, require_family_release=False)
        if not proof["accepted"] or proof["family_id"] != f"F{index}":
            raise ValueError("Need complete, qualified F1/F2/F3 input runs in that order")
        rows = [json.loads(l) for l in (folder/"physical_states.jsonl").read_text().splitlines()]
        selected = [f["frame"] for f in rows if f["stage"] in (f"family_F{index}_ring_approach", f"family_F{index}_corridor")]
        if not selected:
            raise ValueError("Family route is missing")
        lo, hi = max(0, selected[0]-20), min(len(rows), selected[-1]+21)
        # Preserve 1x physical time, no trajectory interpolation or speed-up.
        prepared.append(rows[lo:hi:2])
        proofs.append(proof)
        inputs.append(dict(instance_id=proof["instance_id"], selected_frames=[f["frame"] for f in prepared[-1]],
            result_sha256=file_hash(folder/"result.json"), states_sha256=file_hash(folder/"physical_states.jsonl")))
    output.mkdir(parents=True, exist_ok=False)
    rig = json.loads((folders[0]/"recording_cameras.json").read_text())
    cameras = ["cam_high", "cam_low"]
    for camera in cameras:
        rig[camera]["res"] = [640, 360]
        rig[camera]["fov"] = max(rig[camera]["fov"], 66.)
    gs.init(backend=gs.cpu, precision="64", seed=0, logging_level="warning")
    tasks = []
    for i, folder in enumerate(folders, 1):
        cfg = OmegaConf.load(folder/"config.yaml")
        cfg.env.cameras = OmegaConf.create({c: rig[c] for c in cameras})
        cfg.task.template_path = str(folder/"input_template.json")
        # Keep each successfully executed geometry and actual states; remove
        # the finish cue so route recognition cannot rely on ring color.
        cfg.task.appearance.target_ring_rgba = [.72, .76, .80, 1.]
        tasks.append(build_scene(cfg, output/f"render_assets_F{i}"))
        OmegaConf.save(cfg, output/f"render_config_F{i}.yaml", resolve=True)
    total = max(map(len, prepared))
    with ExitStack() as stack:
        writers = {c: stack.enter_context(imageio.get_writer(output/f"{c}.mp4", fps=10,
            codec="libx264", quality=8, macro_block_size=1, ffmpeg_params=["-threads", "2"])) for c in cameras}
        for k in range(total):
            panels = {c: [] for c in cameras}
            for rows, task in zip(prepared, tasks):
                robot = task.manifest.get("robot")
                # Hold the final selected image once a shorter segment ends.
                frame = rows[min(k, len(rows)-1)]
                robot.set_qpos(np.asarray(frame["qpos"]), zero_velocity=True)
                for name, body in task.bodies.items():
                    pose = frame["bodies"][name]
                    body.set_pos(np.asarray(pose["pos"]))
                    body.set_quat(np.asarray(pose["quat_wxyz"]))
                task.scene.visualizer.update_visual_states(force_render=True)
                for c in cameras:
                    panels[c].append(task.cameras[c].render(force_render=True)[0])
            for c in cameras:
                combined = np.concatenate(panels[c], axis=1)
                writers[c].append_data(combined)
                if k % 10 == 0:
                    Image.fromarray(combined).save(output/f"review_{c}_{k:04d}.jpg")
            if k % 20 == 0:
                print(f"Family comparison: {k+1}/{total}", flush=True)
    (output/"selected_states.json").write_text(json.dumps(prepared))
    report = dict(classification="partial_same_camera_family_comparison", order_left_to_right=["F1", "F2", "F3"],
        source_complete_physical_runs=True, counts_as_complete_robotics_demo=False,
        exact_measured_states=True, physics_steps_during_render=0, playback_speed=1, overlays=False,
        shorter_segments="hold last selected frame", frames=total, fps=10, duration_s=total/10,
        appearance="All rings displayed in the same silver finish for motion review; each run retains its actual geometry/scale",
        per_family_frames=list(map(len, prepared)), sources=inputs, physical_qualification=proofs,
        videos={c: dict(file=c+".mp4", sha256=file_hash(output/(c+".mp4"))) for c in cameras})
    (output/"report.json").write_text(json.dumps(report, indent=2))
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("folders", nargs=3, type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    render(args.folders, args.output)


if __name__ == "__main__":
    main()
