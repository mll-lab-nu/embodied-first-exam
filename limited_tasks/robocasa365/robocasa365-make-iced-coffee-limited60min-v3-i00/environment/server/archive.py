"""Bounded, pickle-free NPZ loader reused from the accepted MetaWorld task."""
from pathlib import Path
import hashlib
import zipfile
import numpy as np

def load_npz(path, max_bytes=2_000_000):
    path = Path(path)
    if path.stat().st_size > max_bytes:
        raise ValueError("archive is too large")
    with zipfile.ZipFile(path) as archive:
        if len(archive.infolist()) > 40 or sum(x.file_size for x in archive.infolist()) > max_bytes * 2:
            raise ValueError("expanded archive is too large")
        names = archive.namelist()
        if len(set(names)) != len(names):
            raise ValueError("duplicate archive members")
        for member in archive.infolist():
            if not member.filename.endswith(".npy"):
                raise ValueError("expected NPY members")
            with archive.open(member) as stream:
                version = np.lib.format.read_magic(stream)
                if version == (1, 0):
                    shape, _, dtype = np.lib.format.read_array_header_1_0(stream)
                elif version == (2, 0):
                    shape, _, dtype = np.lib.format.read_array_header_2_0(stream)
                else:
                    raise ValueError("unsupported NPY version")
                size = dtype.itemsize
                for dim in shape:
                    size *= dim
                if dtype.hasobject or size > max_bytes * 2 or size != member.file_size - stream.tell():
                    raise ValueError("invalid NPY allocation or payload")
    with np.load(path, allow_pickle=False) as data:
        return {k: data[k].copy() for k in data.files}


def digest(data):
    sha = hashlib.sha256()
    for key, value in sorted(data.items()):
        arr = np.ascontiguousarray(value)
        sha.update(key.encode())
        sha.update(arr.dtype.str.encode())
        sha.update(str(arr.shape).encode())
        sha.update(arr.tobytes())
    return sha.hexdigest()


