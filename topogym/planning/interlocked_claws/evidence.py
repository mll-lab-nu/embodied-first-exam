"""Read the shared runner's array references without dropping physical fields."""
import hashlib
from pathlib import Path

import numpy as np


def decode_record(row, private, *, digest=None):
    root = Path(private).resolve()
    chunks = {}

    def decode(value):
        if isinstance(value, dict):
            if {"array_file", "key", "shape", "dtype", "chunk_id"} <= value.keys():
                path = (root/value["array_file"]).resolve()
                if not path.is_relative_to(root/"arrays"):
                    raise ValueError("Array evidence escapes its run directory")
                if path not in chunks:
                    payload = path.read_bytes()
                    if digest is not None:
                        digest.update(value["array_file"].encode()+hashlib.sha256(payload).digest())
                    with np.load(path, allow_pickle=False) as arrays:
                        chunks[path] = {key: arrays[key] for key in arrays.files}
                array = chunks[path][value["key"]]
                if list(array.shape) != value["shape"] or str(array.dtype) != value["dtype"]:
                    raise ValueError("Array evidence shape/dtype mismatch")
                return array
            return {key: decode(child) for key, child in value.items()}
        if isinstance(value, list):
            return [decode(child) for child in value]
        return value

    return decode(row)
