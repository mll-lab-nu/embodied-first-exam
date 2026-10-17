# MuJoCo 3.14.0 wheel + the EPA horizon fix (byte patch)

## The bug
- **What happens:** eket replays crashed MuJoCo 3.14.0 with SIGSEGV in `mj_narrowphase`, when a dowel cylinder is
  pressed into a thin convex mesh piece (top_dowel_3 / side_b_c064, top_dowel_4 / side_a_c059).
- **Why:**
  - EPA (`engine_collision_gjk.c`) stores the polytope horizon in two fixed 24-entry int arrays, whatever
    `ccd_iterations` is, and `addEdge` never checks the bound.
  - With the scenes' `ccd_iterations="500" ccd_tolerance="1e-10"`, EPA grows polytopes of 50-60 vertices with
    horizons of 25-27 edges. The writes past the arrays corrupt memory.
  - An instrumented build counted such overflows in 1 of 394 eket stress episodes and 0 of 290 in the other scenes.
- **Upstream fix:** google-deepmind/mujoco commit 6d662aedda693a1225a03a26c6b3ddd5e3cc4fbe (#3646, released in 3.15).
  - It sizes the arrays `24 + max(0, ccd_iterations - 35)`.
  - It bounds-checks them, stopping EPA with a warning on overflow.
- **Reproducers:** nine eket states from the stress test and from slowed references; they give rc -11 (SIGSEGV) on the
  wheel.

## Why a byte patch, not a source build
A source build of 3.14.0 is not bit-identical to the PyPI wheel's `libmujoco.so`, even unpatched and with the same
clang/lld 20.1.8.
- Measured with the unpatched source build: all 8 references end on other hashes, and ikea365, vesken, eket and
  variera lose their goal.
- So a source build with the upstream patch is **not used: not bit-identical**.
- `bytepatch_libmujoco.py` changes the wheel's own `.so` instead: 14 bytes at 5 sites.

| site (vaddr) | function | old | new |
|---|---|---|---|
| 0x1a7dd0 | mjc_ccd | `lea 0x60(%rcx,%rsi,8),%rcx` (edges = indices + 96 B) | `lea (%rdx,%rsi,8),%rcx; nop` (edges = indices + 48·N B) |
| 0x1a78fb | mjc_ccdSize | `add $0xc0` (2 × 96 B of horizon) | `add $0x10000` |
| 0x196996 | mjc_penetration (inlined mjc_ccdSize) | `add $0x250` (= 400 + 0xc0) | `add $0x10190` |
| 0x19ef12 | mj_narrowphase (inlined) | `add $0x250` | `add $0x10190` |
| 0x2cd612 | mj_geomDistance (inlined) | `add $0x250` | `add $0x10190` |

- The indices array then holds 12·N entries. That is more than the polytope's 5+N vertices; a horizon is a cycle of
  polytope vertices.
- The edges array gets the rest of the 64 KB.
- sha256: wheel `5e7623e30f55bf324d4c9648379ebeba5bcd153ee0304c52eac74bf8d441000b` → patched
  `52e2a24e927ccac047b13576ff9fcbe455bc9a12b0d2e0bf1868bb7ca5be2e4d`. The script asserts both, and every original byte.

**Caveats**
- There is no warning path: EPA simply continues correctly past 24 edges. With ccd_iterations 500, upstream would not
  warn either; its limit is 489.
- It needs `ccd_iterations <= 1259`.
- Each ccd stack allocation grows by 64 KB (fine with the scenes' `memory="1G"`).
- It is only for this exact wheel `.so`: x86_64, mujoco 3.14.0, the sha256 above.

## Gates (Intel Xeon Platinum 8592+, SIMD-masked, patched .so bound over the wheel's, 2026-10-15)
The references of that day (the demos before the joint-speed clamp); the shipped references run on the patched wheel only.

| reference | end hash | after the 1.0 s hold | stock = patched |
|---|---|---|---|
| lack | 07e54fc3728e07e9 | bd20815b73d0ebb7 | yes, success |
| ikea365 | 30d9b427852efe75 | 24d92725a3319976 | yes, success |
| svallet | 08d5450447527d27 | 7919c8b7d3b3f21d | yes, success |
| vesken | c952567d6ac5f1de | da357d1609b06346 | yes, success |
| eket | 61e4bbb2bbed6f7f | f7b8f035f0e10e05 | yes, success |
| burvik | 509ad4fd28740b8b | 976f0223c00c2621 | yes, success |
| gladom | 694488c188f0161b | fdaadce21eaf91ce | yes, success |
| variera (with its release tail) | 65f124f47810b263 | 974093ba600eaeeb | yes, success |

- 52 stress episodes (8 scenes, all strategies): 52 of 52 end on the stock hash.
- The 9 eket crash reproducers: the
  stock wheel crashes on 7 of them. The patched build crashes on none, and gives the same hash in two fresh processes each.

## Use (consumer image, right after `pip install mujoco==3.14.0`)
```dockerfile
COPY bytepatch_libmujoco.py /tmp/bytepatch_libmujoco.py
RUN python /tmp/bytepatch_libmujoco.py \
      "$(python -c 'import mujoco, os; print(os.path.dirname(mujoco.__file__))')/libmujoco.so.3.14.0" \
 && rm /tmp/bytepatch_libmujoco.py
```
The build fails if the installed `.so` is not the expected wheel's.
