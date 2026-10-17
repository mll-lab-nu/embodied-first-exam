#!/usr/bin/env python3
"""Byte-patch the PyPI mujoco==3.14.0 wheel's libmujoco.so.3.14.0 in place so that EPA's horizon arrays cannot
overflow (the eket SIGSEGV; upstream fix 6d662aed, MuJoCo 3.15+). Standard library only.

    python bytepatch_libmujoco.py <site-packages>/mujoco/libmujoco.so.3.14.0

The wheel keeps horizon.indices and horizon.edges as two 24-int arrays (96 bytes each) after the polytope's face map,
whatever ccd_iterations is; addEdge writes past them. 5 sites, 14 bytes:
  1. mjc_ccd (vaddr 0x1a7dd0): edges = indices + 0x60   `lea 0x60(%rcx,%rsi,8),%rcx`  48 8d 4c f1 60
                              -> edges = indices + 48*N  `lea (%rdx,%rsi,8),%rcx; nop` 48 8d 0c f2 90
     (rdx = indices = map + 8*6N, rsi = 6N): indices hold 12N entries, more than the polytope's 5+N vertices.
  2-5. the EPA buffer's horizon term 0xc0 (2 x 96) -> C = 0x10000 in mjc_ccdSize (0x1a78fb) and its three inlined
     copies, where it is folded into 0x250 = 400 + 0xc0 (mjc_penetration 0x196996, mj_narrowphase 0x19ef12,
     mj_geomDistance 0x2cd612). C covers 48N + 4(5+N) bytes for ccd_iterations N <= 1259.
The input and output sha256 are asserted, and every original byte; the file is replaced atomically.
"""
import hashlib, os, sys

SHA_IN = "5e7623e30f55bf324d4c9648379ebeba5bcd153ee0304c52eac74bf8d441000b"
SHA_OUT = "52e2a24e927ccac047b13576ff9fcbe455bc9a12b0d2e0bf1868bb7ca5be2e4d"
TEXT_DELTA = 0x1000            # .text: vaddr 0x1190e0 at file offset 0x1180e0
C = 0x10000


def imm(v):
    return v.to_bytes(4, "little")


SITES = [  # (vaddr, old bytes, new bytes)
    (0x1a7dd0, bytes.fromhex("488d4cf160"), bytes.fromhex("488d0cf290")),
    (0x1a78fb, bytes.fromhex("4881c1") + imm(0xc0), bytes.fromhex("4881c1") + imm(C)),
    (0x196996, bytes.fromhex("4881c1") + imm(0x250), bytes.fromhex("4881c1") + imm(0x250 - 0xc0 + C)),
    (0x19ef12, bytes.fromhex("4881c6") + imm(0x250), bytes.fromhex("4881c6") + imm(0x250 - 0xc0 + C)),
    (0x2cd612, bytes.fromhex("4881c1") + imm(0x250), bytes.fromhex("4881c1") + imm(0x250 - 0xc0 + C)),
]


def main(path):
    b = bytearray(open(path, "rb").read())
    sha = hashlib.sha256(b).hexdigest()
    if sha == SHA_OUT:
        print(f"{path}: already patched ({SHA_OUT})")
        return 0
    if sha != SHA_IN:
        raise SystemExit(f"{path}: sha256 {sha} is not the mujoco 3.14.0 wheel's libmujoco.so ({SHA_IN})")
    changed = 0
    for va, old, new in SITES:
        off = va - TEXT_DELTA
        if bytes(b[off:off + len(old)]) != old:
            raise SystemExit(f"{path}: unexpected bytes at {va:#x}: {b[off:off + len(old)].hex()} != {old.hex()}")
        changed += sum(x != y for x, y in zip(old, new))
        b[off:off + len(new)] = new
    out = hashlib.sha256(b).hexdigest()
    if changed != 14 or out != SHA_OUT:
        raise SystemExit(f"patch check failed: {changed} bytes changed, sha256 {out}")
    tmp = path + ".epa.tmp"
    with open(tmp, "wb") as f:
        f.write(b)
    os.chmod(tmp, os.stat(path).st_mode)
    os.replace(tmp, path)
    print(f"{path}: patched {len(SITES)} sites, {changed} bytes; sha256 {SHA_IN[:12]}... -> {SHA_OUT}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    sys.exit(main(sys.argv[1]))
