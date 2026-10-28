from types import SimpleNamespace
import subprocess

import pytest

from humanclaw_bench.experiments.storage import StorageCapacityError, check_storage, parse_gpfs_quota


QUOTA = """mmlsquota:user:HEADER:version:reserved:reserved:filesystemName:quotaType:id:name:blockUsage:blockQuota:blockLimit:blockInDoubt:blockGrace:filesUsage:filesQuota:filesLimit:filesInDoubt:filesGrace:remarks:fid:filesetname:
mmlsquota:user:0:1:::mmfs1:USR:1:test:45012608:1572864000:1572864000:1024:none:747000:750000:750000:100:none:host:22:nvme1-stf:
"""


def test_machine_quota_counts_in_doubt_and_uses_kib():
    quota = parse_gpfs_quota(QUOTA, "nvme1-stf")
    assert quota["free_files"] == 2900
    assert quota["used_bytes"] == 45012608 * 1024
    assert quota["free_bytes"] == (1572864000 - 45012608 - 1024) * 1024
    with pytest.raises(StorageCapacityError, match="found 0"):
        parse_gpfs_quota(QUOTA, "wrong-fileset")


def test_user_quota_blocks_work_even_with_abundant_filesystem_capacity(tmp_path, monkeypatch):
    monkeypatch.setenv("HUMANCLAW_GPFS_FILESET", "nvme1-stf")
    monkeypatch.setattr("os.statvfs", lambda path: SimpleNamespace(f_files=10**9, f_favail=10**8, f_bavail=10**10, f_frsize=4096))
    monkeypatch.setattr(subprocess, "check_output", lambda *args, **kwargs: QUOTA)
    with pytest.raises(StorageCapacityError, match="2900 free files"):
        check_storage(tmp_path, min_free_files=5000)
    assert check_storage(tmp_path, min_free_files=2000)["user_quota"]["free_files"] == 2900


def test_explicit_quota_lookup_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("HUMANCLAW_GPFS_FILESET", "nvme1-stf")
    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired("mmlsquota", 30)
    monkeypatch.setattr(subprocess, "check_output", fail)
    with pytest.raises(StorageCapacityError, match="Cannot verify"):
        check_storage(tmp_path)


def test_shared_filesystem_bytes_can_be_exhausted_before_user_quota(tmp_path, monkeypatch):
    monkeypatch.delenv("HUMANCLAW_GPFS_FILESET", raising=False)
    monkeypatch.setattr("os.statvfs", lambda path: SimpleNamespace(f_files=100000, f_favail=20000, f_bavail=10, f_frsize=4096))
    with pytest.raises(StorageCapacityError, match="free bytes"):
        check_storage(tmp_path)


def test_recorder_checks_before_creating_a_run(tmp_path, monkeypatch):
    from humanclaw_bench.experiments.recorder import TraceRecorder
    def fail(path):
        raise StorageCapacityError("quota blocked")
    monkeypatch.setattr("humanclaw_bench.experiments.recorder.check_storage", fail)
    with pytest.raises(StorageCapacityError, match="quota blocked"):
        TraceRecorder(tmp_path, {})
    assert not list(tmp_path.iterdir())
