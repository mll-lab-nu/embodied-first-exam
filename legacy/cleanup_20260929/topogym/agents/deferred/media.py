"""Publish complete synchronized MP4 segments, without simulator observations."""
import json
from pathlib import Path
import shutil

from topogym.agent_bridge.session import write_json
from .suite import file_hash


from topogym.recording.encoding import command, probe
from topogym.recording.media import encode_sequence, extract_frame, mosaic as encode_mosaic


def publish_segment(private, public, manifest_path, index, cameras, dt, *, samples=4):
    """One frame per control tick; segment 0 holds tick 0 for one second.

    MP4 duration is (ticks + 1) * dt, since both endpoints are included. The
    manifest separately records the actual simulated interval, ticks * dt.
    """
    private, public = Path(private), Path(public)
    original = json.loads((private / manifest_path).read_text())
    if not original["frames"]:
        raise RuntimeError("No complete camera frame; cannot publish a video")
    frames = []
    for frame in original["frames"]:
        clean = dict(index=frame["index"], tick=frame["tick"], time_s=frame["time_s"], cameras={})
        for camera in cameras:
            source = private / frame["cameras"][camera]["path"]
            target = public / "frames" / f"segment_{index}" / camera / f"{frame['index']:06d}.png"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            clean["cameras"][camera] = dict(path=target.relative_to(public).as_posix(), sha256=file_hash(target))
        frames.append(clean)
    fps = 20 if index == 0 else 1 / dt
    count = 20 if index == 0 else len(frames)
    videos, inputs = {}, []
    for camera in cameras:
        target = public / camera / f"segment_{index}.mp4"
        target.parent.mkdir(exist_ok=True)
        info = encode_sequence(public / "frames" / f"segment_{index}" / camera / "%06d.png",
                               target, fps=fps, count=count, static=index == 0)
        videos[camera] = dict(path=target.relative_to(public).as_posix(), sha256=file_hash(target), **info)
        # Decode model inputs FROM the archived MP4. Always include both endpoints.
        selected = [0] if index == 0 else sorted({round(i*(count-1)/max(1, samples-1)) for i in range(samples)})
        for n in selected:
            target_frame = public / "inputs" / f"segment_{index}" / camera / f"{n:06d}.png"
            target_frame.parent.mkdir(parents=True, exist_ok=True)
            extract_frame(target, n, target_frame)
            inputs.append(dict(camera=camera, video_frame=n, tick=frames[0]["tick"]+ (n if index else 0),
                time_s=frames[0]["time_s"] + (n*dt if index else 0),
                path=target_frame.relative_to(public).as_posix()))
    # Stable 2x2 camera order, with black padding for a three-view task.
    target = public / f"segment_{index}.mp4"
    mosaic = encode_mosaic([public / video["path"] for video in videos.values()], target, count=count)
    manifest = dict(segment=index, cameras=list(cameras), mosaic=dict(path=target.name,
                    sha256=file_hash(target), **mosaic), videos=videos, frames=frames, model_inputs=inputs,
                    start_tick=frames[0]["tick"], end_tick=frames[-1]["tick"],
                    simulated_duration_s=frames[-1]["time_s"]-frames[0]["time_s"],
                    fps=fps, initial_static_hold=index == 0,
                    requested_steps=original.get("requested_steps", 0),
                    attempted_steps=original.get("attempted_steps", 0),
                    executed_steps=original.get("executed_steps", 0))
    write_json(public / f"segment_{index}.json", manifest)
    return manifest
