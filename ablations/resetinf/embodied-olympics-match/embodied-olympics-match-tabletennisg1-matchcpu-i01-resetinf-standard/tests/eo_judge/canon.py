"""Canonical JSON and content digests for the eo-* records (fwspec common.schema.yaml, Digest).

A JSON record's digest is sha256 over its RFC 8785 (JCS) canonical form, written "sha256:<64 hex>"; a file's digest is
sha256 over its bytes. JCS here: object keys sorted by UTF-16 code units, no insignificant whitespace, strings as
JSON with only the mandatory escapes, numbers in the ECMAScript shortest form (integral values without a fraction,
exponent only below 1e-6 or from 1e21 on). Non-finite numbers are refused. Standard library only (the verifier image
has nothing else).

The platform's one canonical form (FWINT2 10-20): framework/canon.py re-exports it, and the Runner, the Task package
and the Competition compute every digest with it, so a digest written by one is the digest another recomputes.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

PREFIX = "sha256:"


def _number(x) -> str:
    if isinstance(x, bool):                     # bool is an int subclass: handled by the caller
        raise TypeError("bool is not a number")
    if isinstance(x, int):
        return str(x)
    if not math.isfinite(x):
        raise ValueError("non-finite number in a canonical record")
    if x == 0:
        return "0"
    if x.is_integer() and abs(x) < 2 ** 53:    # exact integers: the digits ECMAScript prints
        return str(int(x))
    r = repr(x)                                 # shortest round-trip digits (the same digits ECMAScript picks)
    if "e" not in r and "E" not in r:
        return r[:-2] if r.endswith(".0") else r   # an integral value from 2^53 on: its shortest digits
    mant, exp = r.lower().split("e")
    e = int(exp)
    digits = mant.replace(".", "").lstrip("-")
    sign = "-" if x < 0 else ""
    point = (mant.lstrip("-").find(".") if "." in mant else len(mant.lstrip("-"))) + e   # position of the point
    if -6 < point <= 0:                         # 1e-6 <= |x| < 1: 0.000ddd
        return sign + "0." + "0" * (-point) + digits.rstrip("0")
    if 0 < point <= 21:                         # plain digits (|x| < 1e21)
        if point >= len(digits):
            return sign + digits + "0" * (point - len(digits))
        return sign + digits[:point] + "." + digits[point:]
    m = digits[0] + ("." + digits[1:].rstrip("0") if digits[1:].rstrip("0") else "")
    return f"{sign}{m}e{'+' if point - 1 > 0 else '-'}{abs(point - 1)}"


def _string(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def _encode(x, out: list) -> None:
    if x is None:
        out.append("null")
    elif x is True:
        out.append("true")
    elif x is False:
        out.append("false")
    elif isinstance(x, (int, float)):
        out.append(_number(x))
    elif isinstance(x, str):
        out.append(_string(x))
    elif isinstance(x, dict):
        keys = sorted((str(k) for k in x), key=lambda k: k.encode("utf-16-be"))
        out.append("{")
        for i, k in enumerate(keys):
            if i:
                out.append(",")
            out.append(_string(k))
            out.append(":")
            _encode(x[k] if k in x else x[_key(x, k)], out)
        out.append("}")
    elif isinstance(x, (list, tuple)):
        out.append("[")
        for i, v in enumerate(x):
            if i:
                out.append(",")
            _encode(v, out)
        out.append("]")
    else:
        raise TypeError(f"not a JSON value: {type(x).__name__}")


def _key(d: dict, k: str):
    for kk in d:
        if str(kk) == k:
            return kk
    raise KeyError(k)


def jcs(x) -> bytes:
    """The canonical (JCS) bytes of a JSON value."""
    out: list = []
    _encode(x, out)
    return "".join(out).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(x) -> str:
    """Digest of a JSON record: sha256 over its canonical form."""
    return PREFIX + sha256_hex(jcs(x))


def file_digest(path) -> str:
    """Digest of a file's bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return PREFIX + h.hexdigest()


def bytes_digest(data: bytes) -> str:
    return PREFIX + sha256_hex(data)


def tree_digest(files: dict) -> str:
    """Digest of a set of files {relative name: bytes digest} (the judge's own code)."""
    return digest({"files": dict(sorted(files.items()))})


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
