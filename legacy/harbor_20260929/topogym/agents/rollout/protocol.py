"""Small JSON protocol. No pickle, arbitrary file reads, or environment overrides."""
from collections.abc import Mapping
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import tempfile

API_VERSION = "topogym.rollout.v1"
MAX_MESSAGE = 64 * 1024 * 1024
MAX_SOURCE = 1024 * 1024
SOCKET = "/run/topogym/agent.sock"
ADMIN_SOCKET = "/run/topogym/admin.sock"


def validate_admin(message):
    if not isinstance(message, dict) or message.get("api_version") != API_VERSION:
        raise ProtocolError("invalid_admin_operation")
    if message.get("operation") in {"finish", "cancel", "budget_status"} and set(message) == {"api_version", "operation"}:
        return
    if message.get("operation") == "budget_stop" and set(message) == {"api_version", "operation", "snapshot"}:
        from topogym.agents.usage.budget import FAILURE_REASONS
        snapshot = message["snapshot"]
        if (isinstance(snapshot, dict) and isinstance(snapshot.get("stop"), dict)
                and snapshot["stop"].get("reason") in FAILURE_REASONS
                and isinstance(snapshot["stop"].get("stop_id"), str)
                and snapshot["stop"]["stop_id"] and snapshot.get("closed") is True):
            return
    raise ProtocolError("invalid_admin_operation")


class ProtocolError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def dumps(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":"))


def loads(value):
    def invalid(_):
        raise ProtocolError("nonfinite_number")
    def pairs(items):
        result = {}
        for key, val in items:
            if key in result:
                raise ProtocolError("duplicate_field")
            result[key] = val
        return result
    def number(text):
        value = float(text)
        if not math.isfinite(value):
            raise ProtocolError("nonfinite_number")
        return value
    return json.loads(value, parse_constant=invalid, parse_float=number, object_pairs_hook=pairs)


def atomic_json(path, value, mode=0o644):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".publish-")
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(dumps(value) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _read(stream, size):
    blocks = bytearray()
    while len(blocks) < size:
        part = stream.read(size - len(blocks))
        if not part:
            raise EOFError("Transport closed")
        blocks.extend(part)
    return bytes(blocks)


def receive(stream):
    size = struct.unpack("!I", _read(stream, 4))[0]
    if size > MAX_MESSAGE:
        raise ProtocolError("message_too_large")
    return loads(_read(stream, size))


def send(stream, value):
    data = dumps(value).encode()
    if len(data) > MAX_MESSAGE:
        raise ProtocolError("message_too_large")
    stream.write(struct.pack("!I", len(data)) + data)
    stream.flush()


def encode(value):
    """Array encoding for the internal policy RPC, preserving dtype/shape."""
    import numpy as np
    if isinstance(value, np.ndarray):
        if value.dtype.kind not in "bifu" or value.nbytes > MAX_MESSAGE:
            raise ProtocolError("invalid_array")
        return {"__array__": base64.b64encode(value.tobytes()).decode(),
                "dtype": value.dtype.str, "shape": list(value.shape)}
    if isinstance(value, Mapping):
        if any(not isinstance(k, str) for k in value):
            raise ProtocolError("invalid_mapping")
        return {k: encode(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [encode(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def decode(value):
    import numpy as np
    from topogym.utils.snapshots import freeze
    if isinstance(value, dict):
        if "__array__" in value:
            if set(value) != {"__array__", "dtype", "shape"}:
                raise ProtocolError("invalid_array")
            dtype, shape = np.dtype(value["dtype"]), value["shape"]
            if (dtype.kind not in "bifu" or not isinstance(shape, list) or len(shape) > 8
                    or any(type(n) is not int or n < 0 for n in shape)):
                raise ProtocolError("invalid_array")
            size = math.prod(shape) * dtype.itemsize
            if size > MAX_MESSAGE:
                raise ProtocolError("invalid_array")
            data = base64.b64decode(value["__array__"], validate=True)
            if len(data) != size:
                raise ProtocolError("invalid_array")
            return np.frombuffer(data, dtype=dtype).reshape(shape)
        return freeze({k: decode(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(decode(v) for v in value)
    return value


def validate_submit(message, episode_id):
    if set(message) != {"api_version", "operation", "request_id", "episode_id", "policy"}:
        raise ProtocolError("invalid_fields")
    if message["api_version"] != API_VERSION or message["operation"] != "submit_policy":
        raise ProtocolError("unsupported_protocol")
    if message["episode_id"] != episode_id:
        raise ProtocolError("episode_expired")
    request = message["request_id"]
    if not isinstance(request, str) or not request.strip() or len(request) > 256:
        raise ProtocolError("invalid_request_id")
    policy = message["policy"]
    if not isinstance(policy, dict) or set(policy) != {"source_utf8", "filename", "factory", "parameters"}:
        raise ProtocolError("invalid_policy")
    source, filename = policy["source_utf8"], policy["filename"]
    if not isinstance(source, str) or not source or len(source.encode()) > MAX_SOURCE:
        raise ProtocolError("invalid_source")
    if (not isinstance(filename, str) or not filename or filename in {".", ".."}
            or len(filename) > 255 or any(c in filename for c in "/\\\x00")):
        raise ProtocolError("invalid_filename")
    if policy["factory"] != "create_policy" or not isinstance(policy["parameters"], dict):
        raise ProtocolError("invalid_factory_or_parameters")
    if len(dumps(policy["parameters"]).encode()) > 65536:
        raise ProtocolError("parameters_too_large")
    # Filename is a diagnostic label, never an import path or execution identity.
    identity = {k: policy[k] for k in ("source_utf8", "factory", "parameters")}
    identity["api_version"] = API_VERSION
    return hashlib.sha256(dumps(identity).encode()).hexdigest()
