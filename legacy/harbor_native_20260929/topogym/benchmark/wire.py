"""RCB1 framing implemented by TopoGym from the public wire specification.

Only numeric C-order arrays are accepted. No pickle, object arrays, executable
payloads or implicit decompression are used by the transport decoder.
"""
from __future__ import annotations

import json
import math
import struct

import numpy as np

MAX_REQUEST = 64 * 1024**2
MAX_RESPONSE = 256 * 1024**2
MAX_HEADER = 1024**2


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def json_loads(data):
    def invalid(_):
        raise ValueError("Non-finite JSON number")
    return json.loads(data, object_pairs_hook=_pairs, parse_constant=invalid)


def array(name, data):
    value = np.asarray(data)
    if value.dtype.kind not in "biuf" or value.dtype.itemsize > 8:
        raise ValueError("Only numeric arrays are allowed")
    value = np.ascontiguousarray(value.astype(value.dtype.newbyteorder("<"), copy=False))
    return dict(name=name, kind="array", dtype=value.dtype.str,
                shape=list(value.shape), data=value.tobytes())


def blob(name, data, *, kind="bytes", **metadata):
    return dict(metadata, name=name, kind=kind, data=bytes(data))


def encode(meta, parts=(), *, limit=MAX_RESPONSE):
    descriptors, payloads, names = [], [], set()
    size = 0
    for part in parts:
        entry = {k: v for k, v in part.items() if k != "data"}
        name = entry.get("name")
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("Invalid or duplicate part name")
        names.add(name)
        data = bytes(part["data"])
        size += len(data)
        if size > limit:
            raise ValueError("RCB1 payload exceeds limit")
        entry["len"] = len(data)
        descriptors.append(entry)
        payloads.append(data)
    header = json.dumps(dict(v=1, meta=meta, parts=descriptors),
                        separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(header) > MAX_HEADER or 8 + len(header) + size > limit:
        raise ValueError("RCB1 message exceeds limit")
    return b"RCB1" + struct.pack("<I", len(header)) + header + b"".join(payloads)


def decode(body, *, limit=MAX_RESPONSE):
    if len(body) > limit or len(body) < 8 or body[:4] != b"RCB1":
        raise ValueError("Invalid RCB1 frame")
    length, = struct.unpack("<I", body[4:8])
    if length > MAX_HEADER or 8 + length > len(body):
        raise ValueError("Invalid RCB1 header length")
    header = json_loads(body[8:8 + length])
    if not isinstance(header, dict) or header.get("v") != 1:
        raise ValueError("Unsupported RCB1 version")
    if not isinstance(header.get("meta"), dict) or not isinstance(header.get("parts"), list):
        raise ValueError("Malformed RCB1 header")
    result, cursor = {}, 8 + length
    for entry in header["parts"]:
        if not isinstance(entry, dict):
            raise ValueError("Malformed part descriptor")
        name, size, kind = entry.get("name"), entry.get("len"), entry.get("kind")
        if not isinstance(name, str) or not name or name in result:
            raise ValueError("Invalid or duplicate part name")
        if type(size) is not int or size < 0 or cursor + size > len(body):
            raise ValueError("Invalid part length")
        data = body[cursor:cursor + size]
        cursor += size
        if kind == "array":
            try:
                dtype, shape = np.dtype(entry["dtype"]), entry["shape"]
                if dtype.kind not in "biuf" or dtype.itemsize > 8 or dtype.hasobject:
                    raise ValueError("Unsafe array dtype")
                if not isinstance(shape, list) or len(shape) > 8 or any(type(n) is not int or n < 0 for n in shape):
                    raise ValueError("Invalid array shape")
                if math.prod(shape) * dtype.itemsize != size:
                    raise ValueError("Array byte count mismatch")
                data = np.frombuffer(data, dtype=dtype).reshape(shape)
            except (KeyError, TypeError, OverflowError) as exc:
                raise ValueError("Invalid array descriptor") from exc
        elif kind not in {"bytes", "mp4", "jpeg", "json"}:
            raise ValueError("Unsupported part kind")
        result[name] = dict(entry, data=data)
    if cursor != len(body):
        raise ValueError("Trailing RCB1 data")
    return header["meta"], result
