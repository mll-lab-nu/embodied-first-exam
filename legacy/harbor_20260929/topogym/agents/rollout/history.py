"""Read only published segment files, including after the worker has stopped."""
import hashlib
import json
from pathlib import Path
import subprocess

from topogym.utils.io import relative_file


class HistoryReader:
    def __init__(self, root):
        self.root = Path(root).absolute()

    def index(self):
        return json.loads(relative_file(self.root, "history.json").read_text())

    def result(self, segment):
        if type(segment) is not int or segment < 0:
            raise ValueError("Invalid segment ID")
        entries = self.index()["segments"]
        entry = next((item for item in entries if item["segment_id"] == segment), None)
        if entry is None:
            raise ValueError("Segment has not been published")
        result = json.loads(relative_file(self.root, entry["result_relative"]).read_text())
        if result["segment_id"] != segment or result["episode_id"] != self.index()["episode_id"]:
            raise ValueError("History identity mismatch")
        return result

    def artifact(self, descriptor):
        manifest = ("public_artifacts.json" if (self.root / "public_artifacts.json").exists()
                    else "publication.json")
        entry = json.loads(relative_file(self.root, manifest).read_text())["artifacts"][descriptor["artifact_id"]]
        path = relative_file(self.root, entry["archive_relative"])
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if path.stat().st_size != descriptor["size_bytes"] or digest.hexdigest() != descriptor["sha256"]:
            raise ValueError("Published artifact integrity failure")
        return path

    def page(self, segment, kind, start, limit):
        if type(start) is not int or start < 0 or type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("Use start >= 0 and limit in [1, 1000]")
        result = self.result(segment)
        descriptor = (result["media"]["frame_map"] if kind == "frames" else result["logs"][kind])
        rows = []
        with self.artifact(descriptor).open() as stream:
            for index, line in enumerate(stream):
                if index >= start:
                    rows.append(json.loads(line))
                    if len(rows) > limit:
                        break
        return dict(segment_id=segment, kind=kind, start=start, rows=rows[:limit],
                    next_start=start + limit if len(rows) > limit else None)

    def video(self, segment, camera):
        result = self.result(segment)
        descriptor = result["media"]["videos"].get(camera)
        if descriptor is None:
            raise ValueError("No published video for this camera")
        return dict(segment_id=segment, camera=camera, path=str(self.artifact(descriptor)),
                    fps=result["media"]["fps"], frame_count=result["media"]["frame_count"])

    def frames(self, segment, camera, indices, output):
        video = self.video(segment, camera)
        count = video["frame_count"]
        if indices is None:
            indices = sorted({round(i * (count - 1) / 5) for i in range(6)})
        if not indices or len(indices) > 20 or any(type(i) is not int or not 0 <= i < count for i in indices):
            raise ValueError("Select 1 to 20 valid video frame indices")
        indices = sorted(set(indices))
        mappings = {}
        result = self.result(segment)
        with self.artifact(result["media"]["frame_map"]).open() as stream:
            for line in stream:
                row = json.loads(line)
                if row["video_frame_index"] in indices:
                    mappings[row["video_frame_index"]] = row
        if len(mappings) != len(indices):
            raise ValueError("Missing frame/state mapping")
        output = Path(output).resolve()
        if output == self.root.resolve() or self.root.resolve() in output.parents:
            raise ValueError("Extract frames outside the read-only rollout directory")
        output.mkdir(parents=True, exist_ok=False)
        frames = []
        for index in indices:
            target = output / f"frame_{index:06d}.png"
            command = ["ffmpeg", "-v", "error", "-nostdin", "-n", "-threads", "1", "-i", video["path"],
                       "-vf", f"select=eq(n\\,{index})", "-vsync", "0", "-frames:v", "1", "-threads", "1", str(target)]
            encoded = subprocess.run(command, capture_output=True, timeout=120)
            if encoded.returncode or not target.is_file():
                raise ValueError("Video frame extraction failed")
            frames.append(dict(path=str(target), **mappings[index]))
        answer = dict(segment_id=segment, camera=camera, frames=frames)
        (output / "frames.json").write_text(json.dumps(answer, indent=2) + "\n")
        return answer
