"""Export a trajectory comparison from audited physical states, not a robot demo."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

import imageio.v2 as imageio
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial.transform import Rotation

from .long_stroke import relative
from .variants import ASSETS, file_sha, save


def review(root, output, video, run_suffix="release_physics"):
    root, output, video = map(Path, (root, output, video))
    if video.exists() or video.suffix != ".mp4":
        raise ValueError("A new independent MP4 path is required")
    output.mkdir(parents=True, exist_ok=True)
    video.parent.mkdir(parents=True, exist_ok=True)
    baseline = json.loads((ASSETS / "baseline_robot_motion.json").read_text())
    base_xyz = np.array([relative(f)[1] * 1000 for f in baseline["frames"]])
    rows = {}
    for family in ("F1", "F2", "F3"):
        folder = root / f"{family}_{run_suffix}/instance"
        q = json.loads((folder / "qualification.json").read_text())
        if not q["passed"] or q["geometry_sha256"] != file_sha(folder / "geometry.json") or q["solution_sha256"] != file_sha(folder / "robot_motion.json"):
            raise ValueError("Stale qualification")
        for sub, checks in q["physics"].items():
            for name, field in (("report.json", "report_sha256"), ("audit.json", "audit_sha256"), ("trajectory.json", "trajectory_sha256")):
                if file_sha(folder / sub / name) != checks[field]:
                    raise ValueError("Physical evidence changed")
        states = json.loads((folder / "robot_physics/trajectory.json").read_text())
        poses = [relative(f) for f in states]
        xyz = np.array([t * 1000 for _, t in poses])
        gate_index = [i for i, f in enumerate(states) if f["stage"] == "align_right_tooth"][-1]
        angles = np.degrees([Rotation.from_matrix(r @ poses[gate_index][0].T).magnitude() for r, _ in poses])
        rows[family] = dict(folder=folder, proof=q, states=states, xyz=xyz, angles=angles,
            times=np.array([f["time_s"] for f in states]))
    fig, axes = plt.subplots(2, 3, figsize=(16, 8), gridspec_kw=dict(height_ratios=[3, 1]))
    fig.subplots_adjust(top=.87, bottom=.09, wspace=.23, hspace=.30)
    fig.suptitle("Cast Keyhole v2 | actual physics trajectories in the gold-piece frame", fontsize=16)
    fig.text(.5, .925, "Trajectory analysis, not robot-camera video | pregrasp + contact-assisted grasp | one execution per column", ha="center", fontsize=10)
    features = {"F1": "Long passage: 50.88 mm (+19.08 mm)",
                "F2": "Cap detour: +24 mm lateral / +12 mm upward",
                "F3": "Chamber turn: 25 deg, then return 25.5 mm"}
    artists = {}
    for col, (family, row) in enumerate(rows.items()):
        ax, angle_ax = axes[:, col]
        ax.plot(base_xyz[:, 0], base_xyz[:, 1], color="#b4bac0", lw=2, label="original solved IK")
        ax.plot(row["xyz"][:, 0], row["xyz"][:, 1], color="#c3deef", lw=2, label="new physical execution")
        trail, = ax.plot([], [], color="#097dba", lw=3)
        dot, = ax.plot([], [], "o", color="#e66d27", ms=8)
        arrow, = ax.plot([], [], color="#e66d27", lw=3)
        ax.set(xlim=(-15, 85), ylim=(-185, 170), xlabel="relative X (mm)", ylabel="relative Y (mm)")
        ax.set_aspect("equal", adjustable="box")
        ax.grid(alpha=.25)
        ax.set_title(family + " | " + features[family], fontsize=10)
        if col == 0:
            ax.legend(loc="upper left", fontsize=8)
        angle_ax.plot(row["times"], row["angles"], color="#097dba")
        cursor = angle_ax.axvline(0, color="#e66d27")
        angle_ax.set(xlim=(0, 29), ylim=(0, 130), xlabel="physics time (s)", ylabel="angle to gate pose (deg)")
        angle_ax.grid(alpha=.25)
        caption = angle_ax.text(.02, .05, "", transform=angle_ax.transAxes, fontsize=8)
        artists[family] = trail, dot, arrow, cursor, caption
    # Only nearest saved states; the chart never invents in-between physics.
    fps = 12
    duration = max(r["times"][-1] for r in rows.values())
    frame_indices = {f: [] for f in rows}
    with imageio.get_writer(video, fps=fps, codec="libx264", quality=8,
                           ffmpeg_params=["-threads", "2"], macro_block_size=1) as writer:
        for time in np.arange(0, duration + 1/fps, 1/fps):
            for family, row in rows.items():
                index = int(np.argmin(abs(row["times"] - time)))
                frame_indices[family].append(index)
                trail, dot, arrow, cursor, caption = artists[family]
                xy = row["xyz"][:index+1, :2]
                trail.set_data(xy[:, 0], xy[:, 1])
                dot.set_data([xy[-1, 0]], [xy[-1, 1]])
                r, _ = relative(row["states"][index])
                end = xy[-1] + (r @ np.array([0., 18., 0.]))[:2]
                arrow.set_data([xy[-1, 0], end[0]], [xy[-1, 1], end[1]])
                cursor.set_xdata([row["times"][index]] * 2)
                caption.set_text(row["states"][index]["stage"].replace("_", " "))
            fig.canvas.draw()
            writer.append_data(np.asarray(fig.canvas.buffer_rgba())[..., :3])
        fig.savefig(output / "trajectory_comparison.png", dpi=150)
    plt.close(fig)
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"], check=True)
    probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
        "-show_entries", "stream=nb_read_frames,duration,avg_frame_rate,width,height", "-of", "json", str(video)]))["streams"][0]
    save(output / "trajectory_review.json", dict(passed=True,
        classification="analysis_video_of_three_independent_physical_runs_not_robot_demo",
        video=str(video.resolve()), video_sha256=file_sha(video), decoded=True, video_properties=probe,
        source_trace_sha256={f: file_sha(r["folder"] / "robot_physics/trajectory.json") for f, r in rows.items()},
        source_state_indices=frame_indices, coordinate_frame="gold_piece", orientation_arrow_length_mm=18,
        features=features, automatic_human_perceptual_validation=False))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--validation-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--video", type=Path, required=True)
    p.add_argument("--run-suffix", default="release_physics")
    args = p.parse_args()
    review(args.validation_root, args.output, args.video, args.run_suffix)


if __name__ == "__main__":
    main()
