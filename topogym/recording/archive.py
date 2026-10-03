"""Archive a validated synchronous recording with self-contained evidence."""
from pathlib import Path
import shutil

from topogym.recording.encoding import probe
from topogym.utils.io import sha256_file, write_json_atomic


def archive_recording(videos, destination, metadata_dir, *, evidence, metadata):
    """Copy a new demo group; never replace an existing camera or evidence tree.

    ``videos`` maps camera names to MP4s from one shared RecordingSession.
    ``evidence`` maps relative archive paths to files/directories. The caller
    supplies task qualification and recording provenance in ``metadata``.
    All media are decoded, checked for synchrony, and hashed before publishing.
    """
    destination, metadata_dir = Path(destination), Path(metadata_dir)
    if destination.exists() or metadata_dir.exists():
        raise FileExistsError("Use a new archive identity; existing demos are protected")
    if len(videos) < 3:
        raise ValueError("A complete robot demonstration requires at least three views")
    details = {name: probe(path) for name, path in videos.items()}
    if len({(v["frames"], v["fps"], v["width"], v["height"]) for v in details.values()}) != 1:
        raise ValueError("Camera videos are not synchronized")
    for name in videos:
        if Path(name).name != name or name in {"", ".", ".."}:
            raise ValueError("Camera name must be one safe path component")
    for relative in evidence:
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Evidence paths must stay within their archive")
    metadata_dir.mkdir(parents=True)
    manifest = dict(metadata, source_videos={k: str(Path(v).resolve()) for k, v in videos.items()},
                    videos={}, evidence={}, status="copying")
    write_json_atomic(metadata_dir / "archive_manifest.json", manifest)

    def copy_file(source, target):
        target.parent.mkdir(parents=True, exist_ok=True)
        expected = sha256_file(source)
        shutil.copy2(source, target)
        if sha256_file(target) != expected:
            raise IOError("Archive copy failed its hash check: " + str(target))
        return expected

    for relative, source in evidence.items():
        source = Path(source)
        if source.is_dir():
            for file in sorted(source.rglob("*")):
                if file.is_file():
                    target = Path(relative) / file.relative_to(source)
                    manifest["evidence"][str(target)] = copy_file(file, metadata_dir / target)
        else:
            manifest["evidence"][str(relative)] = copy_file(source, metadata_dir / relative)
    for camera, source in videos.items():
        target = destination / camera / (destination.name + "_" + camera + ".mp4")
        digest = copy_file(source, target)
        manifest["videos"][camera] = dict(path=str(target.resolve()), sha256=digest, **details[camera])
    manifest["status"] = "passed"
    write_json_atomic(metadata_dir / "archive_manifest.json", manifest)
    return manifest
