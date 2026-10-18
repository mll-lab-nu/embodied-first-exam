"""Oracle trajectories stored as several archives (each below the repository's 2 MB file limit).

`trajectory.json` lists `trajectory.partNN.npz` files in order; each holds an `actions` slice (float64). The oracle
concatenates them (deflate or LZMA members), checks the sha256 of the concatenated little-endian float64 rows against the manifest and only then
uses them, so the rows are bit-exact. A single `trajectory.npz` is used as it is.
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import zipfile

import numpy as np


def rows_sha256(rows: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(rows, dtype="<f8").tobytes()).hexdigest()


def load(directory: Path) -> tuple[np.ndarray, str]:
    """(actions float64, hand) from `trajectory.json` + parts, or from `trajectory.npz`."""
    directory = Path(directory)
    manifest_path = directory / "trajectory.json"
    if not manifest_path.is_file():
        with np.load(directory / "trajectory.npz", allow_pickle=False) as archive:
            rows = np.asarray(archive["actions"], dtype=np.float64)
            hand = str(archive["hand"]) if "hand" in archive.files else "sharpa"
        return rows, hand
    manifest = json.loads(manifest_path.read_text())
    pieces = []
    for part in manifest["parts"]:
        raw = (directory / part["file"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != part["sha256"]:
            raise ValueError(f"solution part {part['file']} does not match its sha256")
        with np.load(io.BytesIO(raw), allow_pickle=False) as archive:
            pieces.append(np.asarray(archive["actions"], dtype=np.float64))
    rows = np.concatenate(pieces)
    if rows.shape != (manifest["rows"], manifest["width"]) or rows_sha256(rows) != manifest["rows_sha256"]:
        raise ValueError("concatenated solution rows do not match the manifest sha256")
    return rows, manifest.get("hand", "sharpa")


COMPRESSION = {"deflate": zipfile.ZIP_DEFLATED, "lzma": zipfile.ZIP_LZMA}


def _archive(actions: np.ndarray, compression: str = "lzma") -> bytes:
    """A deterministic compressed .npz (fixed zip timestamps) holding one `actions` array."""
    array = io.BytesIO()
    np.lib.format.write_array(array, np.ascontiguousarray(actions, dtype="<f8"), allow_pickle=False)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=COMPRESSION[compression]) as archive:
        info = zipfile.ZipInfo("actions.npy", date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = COMPRESSION[compression]
        archive.writestr(info, array.getvalue())
    return out.getvalue()


def split(source: Path, directory: Path, *, max_bytes: int = 1_900_000, task: str | None = None,
          compression: str = "lzma") -> dict:
    """Write `trajectory.json` + parts below `max_bytes` each into `directory` (authoring time, once)."""
    with np.load(source, allow_pickle=False) as archive:
        rows = np.asarray(archive["actions"], dtype=np.float64)
        hand = str(archive["hand"]) if "hand" in archive.files else "sharpa"
        task = task or (str(archive["task"]) if "task" in archive.files else None)
    count = 2
    while True:
        bounds = np.linspace(0, len(rows), count + 1).round().astype(int)
        blobs = [_archive(rows[a:b], compression) for a, b in zip(bounds[:-1], bounds[1:])]
        if max(len(blob) for blob in blobs) < max_bytes:
            break
        count += 1
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    parts = []
    for index, blob in enumerate(blobs):
        name = f"trajectory.part{index:02d}.npz"
        (directory / name).write_bytes(blob)
        parts.append({"file": name, "rows": int(bounds[index + 1] - bounds[index]), "bytes": len(blob),
                      "sha256": hashlib.sha256(blob).hexdigest()})
    manifest = {"schema_version": 1, "task": task, "hand": hand, "rows": int(len(rows)), "width": int(rows.shape[1]),
                "dtype": "<f8", "rows_sha256": rows_sha256(rows), "source_sha256": hashlib.sha256(Path(source).read_bytes()).hexdigest(),
                "parts": parts}
    (directory / "trajectory.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Split an oracle trajectory into archives below 2 MB")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-bytes", type=int, default=1_900_000)
    parser.add_argument("--task")
    parser.add_argument("--compression", choices=sorted(COMPRESSION), default="lzma")
    args = parser.parse_args()
    print(json.dumps(split(args.input, args.output_dir, max_bytes=args.max_bytes, task=args.task,
                           compression=args.compression), indent=2))
