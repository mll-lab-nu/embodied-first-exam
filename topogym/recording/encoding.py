"""Bounded streaming encoding and common ffmpeg utilities.

Frames are written synchronously to a pipe. Backpressure slows rendering, never
the simulation clock and never silently drops a view.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

from topogym.recording.timeline import positive


def encode_frames(frames, fps):
    """Encode exactly the supplied frame axis, without timeline resampling.

    Used by binary observation responses; the caller owns sampling and its
    frame metadata, while the shared encoder remains the only video writer.
    """
    from tempfile import TemporaryDirectory
    with TemporaryDirectory(prefix="topogym-video-") as directory:
        path = Path(directory) / "frames.mp4"
        writer = VideoWriter(path, fps)
        try:
            for frame in frames:
                writer.append_data(frame)
            writer.close()
            return path.read_bytes()
        except BaseException:
            writer.close(commit=False)
            raise


def command(args, *, timeout=600):
    result = subprocess.run([str(arg) for arg in args], capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace")[-4000:])
    return result.stdout


def probe(path, *, decode=True):
    if decode:
        command(["ffmpeg", "-v", "error", "-xerror", "-nostdin", "-threads", "1",
                 "-i", path, "-f", "null", "-"])
    data = json.loads(command(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,nb_read_frames,duration,avg_frame_rate,codec_name,pix_fmt",
        "-of", "json", path]))
    stream = data["streams"][0]
    numerator, denominator = map(int, stream["avg_frame_rate"].split("/"))
    return dict(width=int(stream["width"]), height=int(stream["height"]), frames=int(stream["nb_read_frames"]),
                duration_s=float(stream["duration"]), fps=numerator / denominator,
                codec=stream["codec_name"], pixel_format=stream["pix_fmt"])


class VideoWriter:
    def __init__(self, path, fps, *, crf=18):
        self.path = Path(path)
        self.fps = positive(fps, "fps")
        self.crf = int(crf)
        if not 0 <= self.crf <= 51:
            raise ValueError("crf must be between 0 and 51")
        self.temporary = self.path.with_suffix(".part.mp4")
        self.log_path = self.path.with_suffix(".encoder.log")
        self.process = self.log = None
        self.shape = None
        self.frames = 0
        self.closed = False
        if self.path.exists() or self.temporary.exists():
            raise FileExistsError(self.path)

    def append_data(self, image):
        import numpy as np
        if self.closed:
            raise RuntimeError("Writer already closed")
        if hasattr(image, "detach"):
            image = image.detach().cpu().numpy()
        image = np.asarray(image)
        if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
            raise ValueError("Video frames must be H x W x 3 uint8 RGB")
        if self.shape is not None and self.shape != image.shape:
            raise ValueError("Camera resolution changed during recording")
        if self.process is None:
            self.shape = image.shape
            height, width, _ = self.shape
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.log = self.log_path.open("wb")
            args = ["ffmpeg", "-v", "error", "-nostdin", "-n", "-f", "rawvideo", "-pix_fmt", "rgb24",
                    "-s", f"{width}x{height}", "-r", str(self.fps), "-i", "pipe:0", "-an",
                    "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-c:v", "libx264", "-threads", "1",
                    "-pix_fmt", "yuv420p", "-crf", str(self.crf), "-movflags", "+faststart", str(self.temporary)]
            try:
                self.process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self.log)
            except BaseException:
                self.log.close()
                raise
        try:
            self.process.stdin.write(np.ascontiguousarray(image).tobytes())
        except (BrokenPipeError, OSError) as error:
            raise RuntimeError(f"Video encoder failed: {self.log_path}") from error
        self.frames += 1

    def close(self, *, commit=True):
        if self.closed:
            return
        self.closed = True
        if self.process is None:
            if commit:
                raise ValueError("Cannot complete an empty video")
            return
        pipe_error = None
        try:
            try:
                self.process.stdin.close()
            except OSError as error:
                pipe_error = error
            try:
                code = self.process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
                raise RuntimeError(f"Encoder close timed out: {self.path}")
        finally:
            self.log.close()
        if code or pipe_error:
            raise RuntimeError(f"Encoder failed: {self.log_path.read_text(errors='replace')[-2000:]}")
        if commit:
            if self.path.exists():
                raise FileExistsError(self.path)
            self.temporary.rename(self.path)

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        try:
            self.close(commit=kind is None)
        except Exception:
            if kind is None:
                raise
