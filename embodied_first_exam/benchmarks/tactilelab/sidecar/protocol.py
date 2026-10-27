"""Wire format of the Newton bridge, protocol v3 (stdlib + numpy only; shared by the client and the sidecar).

The simulation (Isaac Sim, Python 3.11, warp 1.12) cannot import Newton (Python 3.12, warp >= 1.17), so Newton runs in a
sidecar process with its own interpreter.  This module is the language the two processes speak.

Control and data travel on two paths:

* **control**: a unix socket with length-prefixed frames holding a small JSON envelope;
* **arrays**: small ones (<= :data:`INLINE_MAX` bytes) follow the envelope inside the frame as raw bytes; larger ones go
  through shared memory - an :class:`Arena`, one per direction, a file on tmpfs (``/dev/shm``) that the writer fills and
  the reader maps.  A big array costs one ``memcpy`` into the arena (and, if the reader wants it, one out of it) instead
  of a serialisation and several socket copies, and the reader can also look at it in place (``copy=False``).

A *frame* is ``u64 payload length | payload``; a payload is ``u32 envelope length | envelope json | inline array bytes``::

    envelope = {"v": 3, "kind": "req" | "resp" | "event", "id": int, ...kind fields..., "shm": arena size,
                "a": [[name, dtype, shape] (inline) | [name, dtype, shape, arena offset] (shared memory), ...]}
    req      : "op": str, "h": {...}                                   client -> sidecar
    resp     : "ok": bool, "h": {...} | "err": {type, message, traceback}     sidecar -> client (same ``id``)
    event    : "event": str, "h": {...}                                sidecar -> client while request ``id`` runs

Arrays are raw little-endian buffers described by dtype string and shape (no pickle, no object dtype), which is stable
across numpy versions and Python versions - the two processes run different interpreters.  GPU arrays are not handled
here: they cross as host arrays (``.cpu()`` / ``wp.array.numpy()``).

The hot path stays at memory-copy speed: one ``sendmsg`` (scatter-gather, nothing concatenated) and one ``recv`` per small
frame on a persistent buffer (:class:`Conn`), a cached socket timeout, dtype and descriptor parsing without numpy lookups,
and inline arrays sent straight from their own memory.
"""

from __future__ import annotations

import json
import mmap
import os
import socket
import struct
from collections.abc import Mapping, Sequence as SeqABC
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

VERSION = 3
MAX_FRAME = 1 << 31
#: arrays up to this many bytes travel inside the frame; larger ones use the shared-memory arena (if there is one)
INLINE_MAX = 16 * 1024
_ALIGN = 64
_RECV_BUF = 1 << 16

_FRAME = struct.Struct("<Q")
_HEAD = struct.Struct("<I")
_FRAME_HEAD = struct.Struct("<QI")  # frame length and envelope length, sent together (all little-endian)

_DTYPES: Dict[str, np.dtype] = {}


def _dt(s: str) -> np.dtype:
    d = _DTYPES.get(s)
    if d is None:
        d = _DTYPES[s] = np.dtype(s)
    return d


class ProtocolError(RuntimeError):
    pass


def _jsonable(o: Any):
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.floating, np.integer, np.bool_)):
        return o.item()
    if isinstance(o, (set, tuple)):
        return list(o)
    if isinstance(o, Mapping):
        return dict(o)
    if isinstance(o, SeqABC) and not isinstance(o, (str, bytes, bytearray)):
        return list(o)
    raise TypeError(f"not JSON serialisable: {type(o).__name__}")


class Arena:
    """One direction of shared memory: a file the *writer* creates, fills and grows, and the *reader* maps read-only.

    ``put`` copies arrays in at 64-byte aligned offsets (growing the file, by powers of two, when needed) and returns
    their descriptors; ``get`` turns descriptors back into arrays.  The writer reuses the whole arena for every message
    (the peer has consumed the previous one before it replies), so a view obtained with ``copy=False`` is valid only until
    the next message in that direction."""

    def __init__(self, path: str, writer: bool, initial: int = 4 << 20):
        self.path, self.writer, self.initial = path, writer, initial
        self.size = 0
        self._fd: Optional[int] = None
        self._mm: Optional[mmap.mmap] = None

    def put(self, arrays: Dict[str, np.ndarray]) -> List[List[Any]]:
        placed, total = [], 0
        for name, arr in arrays.items():
            off = -(-total // _ALIGN) * _ALIGN
            placed.append((name, arr, off))
            total = off + arr.nbytes
        if total > self.size:
            size = max(self.initial, 1 << (total - 1).bit_length())
            if self._fd is None:
                self._fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_TRUNC, 0o600)
            os.ftruncate(self._fd, size)
            self._mm = mmap.mmap(self._fd, size)  # earlier, smaller mappings stay valid while views of them live
            self.size = size
        assert self._mm is not None
        descs = []
        for name, arr, off in placed:
            dst = np.frombuffer(self._mm, dtype=np.uint8, count=arr.nbytes, offset=off)
            dst[:] = arr.reshape(-1).view(np.uint8)
            descs.append([name, arr.dtype.str, list(arr.shape), off])
        return descs

    def get(self, descs: Sequence[Sequence[Any]], size: int, copy: bool) -> Dict[str, np.ndarray]:
        if self._mm is None or size > self.size:  # first use, or the writer grew the file: map (more of) it
            fd = os.open(self.path, os.O_RDONLY)
            try:
                self._mm = mmap.mmap(fd, size, prot=mmap.PROT_READ)
            finally:
                os.close(fd)
            self.size = size
        out = {}
        for name, t, shape, off in descs:
            n = 1
            for s in shape:
                n *= s
            a = np.frombuffer(self._mm, dtype=_dt(t), count=n, offset=off).reshape(shape)
            out[name] = a.copy() if copy else a
        return out

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        self._mm = None
        self.size = 0


def _parts(
    envelope: Dict[str, Any], arrays: Optional[Dict[str, np.ndarray]], arena: Optional[Arena]
) -> Tuple[bytes, List[Any], int]:
    """The JSON envelope (bytes), the inline array buffers and their total size."""
    env = {"v": VERSION, **envelope}
    blobs: List[Any] = []
    nbytes = 0
    if arrays:
        descs, shm = [], {}
        for name, arr in arrays.items():
            if type(arr) is not np.ndarray:
                arr = np.asarray(arr)
            if not arr.flags["C_CONTIGUOUS"]:  # (ascontiguousarray would turn a 0-d array into a 1-d one)
                arr = np.ascontiguousarray(arr)
            dt = arr.dtype
            if dt.hasobject:
                raise TypeError(f"array {name!r}: object dtype cannot cross the bridge")
            if arena is not None and arr.nbytes > INLINE_MAX:
                shm[name] = arr
                continue
            descs.append([name, dt.str, list(arr.shape)])
            if arr.nbytes:
                blobs.append(arr.reshape(-1).view(np.uint8))  # sent from the array's own memory
                nbytes += arr.nbytes
        if shm:
            assert arena is not None
            descs.extend(arena.put(shm))
            env["shm"] = arena.size
        env["a"] = descs
    return json.dumps(env, separators=(",", ":"), default=_jsonable).encode(), blobs, nbytes


def encode(
    envelope: Dict[str, Any], arrays: Optional[Dict[str, np.ndarray]] = None, arena: Optional[Arena] = None
) -> bytes:
    """``envelope`` (``kind``, ``id``, ...) and named arrays -> one payload (large arrays go to ``arena``)."""
    head, blobs, _ = _parts(envelope, arrays, arena)
    return b"".join([_HEAD.pack(len(head)), head, *(b.tobytes() for b in blobs)])


def decode(
    payload: Any, arena: Optional[Arena] = None, copy: bool = True
) -> Tuple[Dict[str, Any], Dict[str, np.ndarray]]:
    """One payload (bytes-like) -> (envelope, arrays).  With ``copy=False`` arrays from shared memory are read-only views
    of the arena (valid until the peer's next message); inline arrays are always private copies."""
    mv = memoryview(payload)
    (n,) = _HEAD.unpack_from(mv, 0)
    env = json.loads(bytes(mv[_HEAD.size : _HEAD.size + n]))
    if env.get("v") != VERSION:
        raise ProtocolError(f"protocol version {env.get('v')!r}, this side speaks {VERSION}")
    descs = env.pop("a", None)
    arrays: Dict[str, np.ndarray] = {}
    if descs:
        off = _HEAD.size + n
        shm = []
        for d in descs:
            if len(d) == 4:
                shm.append(d)
                continue
            name, t, shape = d
            dt = _dt(t)
            cnt = 1
            for s in shape:
                cnt *= s
            arrays[name] = np.frombuffer(mv, dtype=dt, count=cnt, offset=off).reshape(shape).copy()
            off += cnt * dt.itemsize
        if shm:
            if arena is None:
                raise ProtocolError("shared-memory arrays received but no arena is attached")
            arrays.update(arena.get(shm, int(env["shm"]), copy))
    return env, arrays


class Conn:
    """A framed connection over a stream socket: ``send`` / ``recv`` of (envelope, arrays) with the arenas attached.

    Small frames cost one ``sendmsg`` (header, envelope and array buffers as a scatter list: nothing is concatenated) and
    one ``recv`` into a persistent buffer; the socket timeout is only set when it changes.  A ``recv`` may read past the
    end of a frame (an event frame is usually followed at once by the response): the surplus stays buffered for the next
    call."""

    def __init__(self, sock: socket.socket, tx: Optional[Arena] = None, rx: Optional[Arena] = None):
        self.sock, self.tx, self.rx = sock, tx, rx
        self._buf = bytearray(_RECV_BUF)
        self._r = self._w = 0  # buffered, not yet consumed bytes are _buf[_r:_w]
        self._timeout: Any = -1  # never a valid timeout: forces the first settimeout

    def settimeout(self, t: Optional[float]) -> None:
        if t != self._timeout:
            self.sock.settimeout(t)
            self._timeout = t

    def send(self, envelope: Dict[str, Any], arrays: Optional[Dict[str, np.ndarray]] = None) -> None:
        head, blobs, nbytes = _parts(envelope, arrays, self.tx)
        bufs = [_FRAME_HEAD.pack(_HEAD.size + len(head) + nbytes, len(head)), head, *blobs]
        total = _FRAME_HEAD.size + len(head) + nbytes
        sent = self.sock.sendmsg(bufs)
        if sent < total:  # a big frame filled the socket buffer: finish it the slow way
            rest = b"".join(bytes(b) for b in bufs)[sent:]
            self.sock.sendall(rest)

    def _read_more(self) -> None:
        """One ``recv`` into the free space of the buffer (compacted first if the consumed prefix is in the way)."""
        if self._r == self._w:
            self._r = self._w = 0
        elif self._r and len(self._buf) - self._w < 4096:
            n = self._w - self._r
            self._buf[:n] = self._buf[self._r : self._w]
            self._r, self._w = 0, n
        k = self.sock.recv_into(memoryview(self._buf)[self._w :], len(self._buf) - self._w)
        if k == 0:
            raise EOFError("connection closed")
        self._w += k

    def recv(self, copy: bool = True) -> Tuple[Dict[str, Any], Dict[str, np.ndarray]]:
        while self._w - self._r < _FRAME.size:
            self._read_more()
        (length,) = _FRAME.unpack_from(self._buf, self._r)
        if length > MAX_FRAME:
            raise ProtocolError(f"frame of {length} bytes")
        total = _FRAME.size + length
        if total <= len(self._buf):
            while self._w - self._r < total:
                self._read_more()
            payload = memoryview(self._buf)[self._r + _FRAME.size : self._r + total]
            try:
                return decode(payload, self.rx, copy)
            finally:
                payload.release()
                self._r += total
        # a big inline frame: its own buffer; what is already here is its beginning
        big = bytearray(length)
        have = min(self._w - self._r - _FRAME.size, length)
        big[:have] = memoryview(self._buf)[self._r + _FRAME.size : self._r + _FRAME.size + have]
        self._r += _FRAME.size + have
        mv = memoryview(big)
        while have < length:
            k = self.sock.recv_into(mv[have:], length - have)
            if k == 0:
                raise EOFError("connection closed")
            have += k
        return decode(mv, self.rx, copy)


# One-off helpers (tests): a fresh Conn per call would lose bytes read ahead of the frame, so they are only valid under
# the bridge's request / response discipline, where a frame is the only thing in flight.
def send(
    sock: socket.socket,
    envelope: Dict[str, Any],
    arrays: Optional[Dict[str, np.ndarray]] = None,
    arena: Optional[Arena] = None,
) -> None:
    Conn(sock, tx=arena).send(envelope, arrays)


def recv(
    sock: socket.socket, arena: Optional[Arena] = None, copy: bool = True
) -> Tuple[Dict[str, Any], Dict[str, np.ndarray]]:
    return Conn(sock, rx=arena).recv(copy)
