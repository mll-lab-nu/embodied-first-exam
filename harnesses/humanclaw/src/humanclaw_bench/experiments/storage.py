"""Check filesystem capacity and explicitly configured GPFS user quotas."""

from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import unquote


class StorageCapacityError(OSError):
    """A run must not begin while its output cannot be recorded safely."""


def parse_gpfs_quota(output: str, fileset: str) -> dict[str, int | str]:
    """Read GPFS's machine format; block counters use its default KiB units."""
    headers = {}
    matches = []
    for line in output.splitlines():
        fields = [unquote(value) for value in line.split(":")]
        if len(fields) < 4 or fields[0] != "mmlsquota":
            continue
        key = tuple(fields[:2])
        if fields[2] == "HEADER":
            headers[key] = fields
        elif key in headers:
            row = dict(zip(headers[key], fields))
            if row.get("filesetname") == fileset and row.get("quotaType") == "USR":
                matches.append(row)
    if len(matches) != 1:
        raise StorageCapacityError(f"Expected one user quota for {fileset}; found {len(matches)}")
    row = matches[0]
    def capacity(used, uncertain, soft, hard, factor=1):
        """Subtract usage and in-doubt allocations from the strictest quota."""
        limits = [int(row[name]) for name in (soft, hard) if int(row[name]) > 0]
        if not limits:
            return None
        return max(0, min(limits) - int(row[used]) - int(row[uncertain])) * factor
    try:
        return {
            "fileset": fileset,
            "used_files": int(row["filesUsage"]),
            "free_files": capacity("filesUsage", "filesInDoubt", "filesQuota", "filesLimit"),
            "used_bytes": int(row["blockUsage"]) * 1024,
            "free_bytes": capacity("blockUsage", "blockInDoubt", "blockQuota", "blockLimit", 1024),
        }
    except (KeyError, ValueError) as exc:
        raise StorageCapacityError(f"Invalid GPFS quota counters: {exc}") from exc


def check_storage(directory: str | Path, *, min_free_files: int | None = None,
                  min_free_bytes: int | None = None) -> dict:
    """Fail before paid work; configured quota lookup failure is also an error."""
    path = Path(directory).expanduser().resolve()
    while not path.exists():
        path = path.parent
    min_free_files = int(os.environ.get("HUMANCLAW_MIN_FREE_FILES", "5000")) if min_free_files is None else min_free_files
    min_free_bytes = int(os.environ.get("HUMANCLAW_MIN_FREE_BYTES", str(2 * 1024**3))) if min_free_bytes is None else min_free_bytes
    if min_free_files < 0 or min_free_bytes < 0:
        raise ValueError("Storage reserves must be nonnegative")
    stat = os.statvfs(path)
    # Some filesystems do not implement inode counters (both are zero).
    fs_files = stat.f_favail if stat.f_files else None
    result = {"path": str(path), "filesystem_free_files": fs_files,
              "filesystem_free_bytes": stat.f_bavail * stat.f_frsize,
              "min_free_files": min_free_files, "min_free_bytes": min_free_bytes,
              "user_quota": None}
    fileset = os.environ.get("HUMANCLAW_GPFS_FILESET")
    if fileset:
        try:
            output = subprocess.check_output([
                os.environ.get("HUMANCLAW_MMLSQUOTA", "/usr/lpp/mmfs/bin/mmlsquota"),
                "-u", getpass.getuser(), "-Y", os.environ.get("HUMANCLAW_GPFS_FILESYSTEM", "gpfs"),
            ], text=True, stderr=subprocess.PIPE, timeout=30)
            result["user_quota"] = parse_gpfs_quota(output, fileset)
        except (OSError, subprocess.SubprocessError) as exc:
            raise StorageCapacityError(f"Cannot verify configured GPFS quota: {exc}") from exc
    quota = result["user_quota"] or {}
    for kind, minimum, available in (
        ("files", min_free_files, [fs_files, quota.get("free_files")]),
        ("bytes", min_free_bytes, [result["filesystem_free_bytes"], quota.get("free_bytes")]),
    ):
        known = [value for value in available if value is not None]
        if known and min(known) < minimum:
            raise StorageCapacityError(f"Insufficient output capacity: {min(known)} free {kind}; reserve {minimum}. {json.dumps(result)}")
    return result


def main() -> int:
    """Print capacity details or return 75 when storage cannot be verified."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(check_storage(args.directory)))
    except StorageCapacityError as exc:
        print(str(exc))
        return 75
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
