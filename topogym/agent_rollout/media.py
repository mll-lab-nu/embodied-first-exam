"""Publish complete synchronized MP4 segments, without simulator observations."""
import json
from pathlib import Path
import shutil
import subprocess

from topogym.agent_bridge.session import write_json
from .suite import file_hash


def command(args):
    result = subprocess.run(args, capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace")[-4000:])
    return result.stdout


def probe(path):
    data = json.loads(command(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,nb_read_frames,duration,avg_frame_rate", "-of", "json", str(path)]))
    stream = data["streams"][0]
    return dict(width=int(stream["width"]), height=int(stream["height"]),
                frames=int(stream["nb_read_frames"]), duration_s=float(stream["duration"]))


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
        temp = target.with_suffix(".part.mp4")
        args = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-threads", "1", "-framerate", str(fps)]
        if index == 0:
            args += ["-loop", "1"]
        args += ["-i", str(public / "frames" / f"segment_{index}" / camera / "%06d.png"),
                 "-frames:v", str(count), "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
                 "-c:v", "libx264", "-threads", "1", "-pix_fmt", "yuv420p", "-crf", "18",
                 "-movflags", "+faststart", str(temp)]
        command(args)
        temp.replace(target)
        info = probe(target)
        if info["frames"] != count:
            raise RuntimeError("Encoded frame count mismatch")
        videos[camera] = dict(path=target.relative_to(public).as_posix(), sha256=file_hash(target), **info)
        # Decode model inputs FROM the archived MP4. Always include both endpoints.
        selected = [0] if index == 0 else sorted({round(i*(count-1)/max(1, samples-1)) for i in range(samples)})
        for n in selected:
            target_frame = public / "inputs" / f"segment_{index}" / camera / f"{n:06d}.png"
            target_frame.parent.mkdir(parents=True, exist_ok=True)
            command(["ffmpeg", "-v", "error", "-nostdin", "-y", "-threads", "1", "-i", str(target),
                     "-vf", f"select=eq(n\\,{n})", "-frames:v", "1", "-threads", "1", str(target_frame)])
            inputs.append(dict(camera=camera, video_frame=n, tick=frames[0]["tick"]+ (n if index else 0),
                time_s=frames[0]["time_s"] + (n*dt if index else 0),
                path=target_frame.relative_to(public).as_posix()))
    # Stable 2x2 camera order, with black padding for a three-view task.
    widths, heights = [v["width"] for v in videos.values()], [v["height"] for v in videos.values()]
    width, height = max(widths), max(heights)
    args = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-filter_complex_threads", "1"]
    for video in videos.values():
        args += ["-threads", "1", "-i", str(public / video["path"])]
    filters = [f"[{i}:v]pad={width}:{height}:0:0[v{i}]" for i in range(len(cameras))]
    layout = "|".join(f"{(i%2)*width}_{(i//2)*height}" for i in range(len(cameras)))
    filters.append("".join(f"[v{i}]" for i in range(len(cameras))) +
                   f"xstack=inputs={len(cameras)}:layout={layout}:fill=black[out]")
    target = public / f"segment_{index}.mp4"
    temp = target.with_suffix(".part.mp4")
    command(args + ["-filter_complex", ";".join(filters), "-map", "[out]", "-c:v", "libx264",
                    "-threads", "1", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(temp)])
    temp.replace(target)
    mosaic = probe(target)
    if mosaic["frames"] != count:
        raise RuntimeError("Mosaic frame count mismatch")
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
