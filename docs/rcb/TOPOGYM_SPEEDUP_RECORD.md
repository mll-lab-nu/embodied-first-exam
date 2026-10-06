# TopoGym speed-up record (2026-10-01 to 2026-10-06)

This page records how much faster the TopoGym simulator became between the version used by the 10-01 agent sweep
(tooling v4, image 0.2.5) and merged-v18 (tooling 18, image 0.2.16-dev, `8d7d16489`), measured with one fixed
benchmark. On v4 an agent spent 58-73 % of its 6 h budget waiting for the simulator and executed only 1.3-1.7k
control steps (10-01 sweep). The speed-ups below are what made the 6 h budget mostly reasoning time.

## Summary

- **Per control step:** rigid families 9-22x faster, cloth 13x, rope / slotted / knot / orbits 11-30x. Rope reaches
  about 250x in this benchmark, which measures it near rest.
- **Scene build:** 3-11x faster (about 3-7 min down to 25-60 s).
- **First rendered frame:** from 20+ s down to 0.03-0.3 s, thanks to the warm kernel cache.
- **One full oracle execution** (end to end, lab) now fits the 72 min rule (20 % of 6 h) for 31 of the 33 tasks that
  have an oracle. The exceptions are fiber hard (185 min) and buzz hard (74 min), both accepted.

## Method (same as the 10-03 benchmark)

- Host: lab (TAMU, RTX PRO 6000 Max-Q, EPYC 9534).
- Each family's easy tier runs in a fresh container, alone on its GPU, with no network.
- Measured:
  - `Session(...)` build time;
  - the first `render_frame()`;
  - N control steps of the same small arm wave in every version: each arm joint at `hold + 0.04 sin(2 pi i / 40)`
    rad, grippers held. N is 100 for rigid families, 40 for blanket and 5 for the IPC families.
- Reported value: the median step time.
- Script: lab `topogym_v1/bin/bench_step.py`, run per family by `bin/bench_fam.sh`. Raw lines: lab `topogym_v1/bench/`
  (`old_v4.jsonl`, `new_v10.jsonl`, `new_v10_orbits.jsonl`, `new_v12.jsonl`, `new_v18.jsonl`, `new_v18g.jsonl`).
- Versions:
  - **v4:** root v4 packages + `ghcr.io/luigivamper/rcb-topogym:0.2.5-cu128`, the 10-01 sweep version.
  - **v10 / v12:** the 10-02 round, measured 10-02 / 10-03.
  - **v18:** `cand_v18b` packages + `labv18b/rcb-topogym:0.2.16-dev-cu128`. Its release identity equals the pushed
    `8d7d16489`. Measured 10-06 03:38-03:50 on an otherwise idle host.

| family | backend v4 -> v18 | step v4 (s) | step v10 / v12 (s) | step v18 (s) | step speed-up | build v4 -> v18 (s) |
|---|---|---|---|---|---|---|
| buzz_wire_3d | GPU fp64 -> CPU fp64 | 1.087 | 0.085 | 0.066 | 16.4x | 217 -> 47 (4.7x) |
| cast_coil | GPU fp64 -> CPU fp64 | 0.583 | 0.061 | 0.044 | 13.3x | 183 -> 26 (7.2x) |
| cast_keyhole | GPU fp64 -> CPU fp64 | 0.567 | 0.046 | 0.047 | 12.1x | 179 -> 26 (7.0x) |
| fiber_bundling | GPU fp64 -> CPU fp64 | 2.190 | 0.158 | 0.099 | 22.2x | 240 -> 30 (8.1x) |
| hedgehog_in_cage | GPU fp64 -> CPU fp64 | 1.013 | 0.055 | 0.056 | 18.1x | 214 -> 62 (3.5x) |
| horseshoe_ring | GPU fp64 -> CPU fp64 | 0.672 | 0.067 | 0.071 | 9.5x | 188 -> 34 (5.5x) |
| interlocked_claws | GPU fp64 -> CPU fp64 | 0.573 | 0.054 | 0.064 | 9.0x | 180 -> 28 (6.4x) |
| lock_picking | GPU fp64 -> GPU fp32 | 1.186 | 0.075 | 0.077 | 15.4x | 204 -> 44 (4.6x) |
| blanket_flatten | GPU (PBD) | 3.698 | 0.305 | 0.285 | 13.0x | 183 -> 60 (3.1x) |
| rope_threading | GPU IPC | 39.47 | 2.275 | 0.156 | 253x (near rest) | 445 -> 40 (11.3x) |
| slotted_post_ring | GPU IPC | 26.90 | 2.488 | 2.538 | 10.6x | 207 -> 57 (3.6x) |
| knot_untying | GPU IPC | 32.07 | 4.916 / 2.132 | 1.067 | 30.0x | 194 -> 55 (3.5x) |
| orbits | GPU IPC | 31.12 | - / 2.389 | 2.500 | 12.4x | 229 -> 60 (3.8x) |

Reading the table:
- **The benchmark's motion touches almost nothing.** Contact-heavy phases cost more per step in every version, for
  example fiber's strand combing, knot's approach and rope's threading.
  - The IPC rows measure the first 5 steps from the built scene.
  - Rope's v10 -> v18 drop comes mostly from the cached soft-grasp admission (`6c9bcdae9`), which no longer recomputes
    finger-surface distances every tick. 253x is therefore a near-rest number.
  - End-to-end times are the realistic measure (next table).
- **claws (+17 %) and horseshoe (+6 %) are slightly slower than at v10.** The tooling added per-tick work after v10:
  the BUG 7 state restore and the safety checks. claws' first frame (0.27 s) suggests its render kernels were not in
  the warm cache of this image.

## End to end: one full oracle execution on lab (privileged live, min)

"Before" is the earliest full lab execution, on 10-04, already after the 10-02 round. On v4 these executions were
not feasible: for example rope medium, at about 2900 steps x 39 s, would have taken about 32 h. "v18" is the final
oracle sweep of 10-05/06.

| task | before (10-04) | v18 | speed-up | main cause |
|---|---|---|---|---|
| fiber hard | 989 | 185 | 5.3x | v17 tree-sparse mass factor + children-first order (`6764c2a2e`) |
| fiber medium / easy | 127 / 31 | 56 / 22 | 2.3x / 1.4x | same |
| knot easy / medium / hard | 53 / 174 / 183 | 26 / 62 / 71 | 2.0x / 2.8x / 2.6x | v18 K2: 5 ms IPC frames, semi-implicit Newton >= 3 iterations (`c83285343`) |
| blanket hard | 92 | 60 (29 alone) | 1.5x (3.1x alone) | v18 coverage-union skip + soft-grasp caching |
| buzz medium / hard | 71 / 116 | 37 / 74 | 1.9x / 1.6x | oracle re-timing (O2-8, O2-9; the oracle only) + v18 release evidence (`d8b576d0b`, `d0c501f75`) |
| rope easy / medium | 41 / 53 | 26 / 33 | 1.6x | soft-grasp caching + less GPU contention |
| all other tasks | 3-55 | 2-43 | ~1.0-1.4x | already fast; differences are mostly host load |

## What changed, by version

| version (date) | change | effect on results |
|---|---|---|
| v5 / 0.2.7 (10-02) | batched rigid-state readback | identical |
| v6 / 0.2.8 (10-02) | rigid families in float32; blanket coverage skip; cheaper exact IPC diagnostics | v6 float32 superseded by v7 |
| v7 / 0.2.9 (10-02) | seven rigid families on CPU float64; frames rendered only on request; exact per-tick fast paths | CPU fp64 replays bit-exact |
| v9 / 0.2.10 (10-02) | rope and slotted on one IPC substep from a settled scene; claws back on CPU fp64 | physics setting, dual-validated |
| v10 (10-02) | Jianwen's merge of the above with his repairs | - |
| v11 / 0.2.11 (10-02) | IPC settled states frozen with the instance; knot / orbits settings; blanket evaluation fast paths; warm kernel cache | first frame 20+ s -> < 1 s |
| v12 (10-02) | knot and orbits on one IPC substep; the final-settling check only on reached ticks | physics setting, dual-validated |
| v13 / v14 / 0.2.12 (10-03) | merges; bounded PBD-rigid contact and the instability guard (blanket) | stability fix |
| v17 / 0.2.15 (10-05) | fiber: tree-sparse mass factor, children-first skyline order above 64 DOFs, exact strand / passage fast paths; deterministic GPU physics (PBD fixed-point sums, pinned rigid solve arm) | fiber at round-off level; determinism costs blanket +4 %, lock 0 |
| v18 / 0.2.16 (10-05) | knot K2; blanket coverage-union skip; soft-grasp admission and release-evidence caching; weld-read cache; deterministic libuipc | all identical except K2 (dual-validated) and libuipc (knot +2 %, rope +3-7 %) |

- **Where the speed-ups apply:** every step-time change above is in the image or the runtime tooling, so it speeds up
  agent sessions, the standard-mode service and the grading replays alike. Only the buzz re-timing is oracle-only.
- **Rendering:**
  - privileged sessions render a frame only when the agent asks (`render_frame` and similar, since v7);
  - the standard service renders at the frame rate the agent requests for each call (default 10 frames per simulated
    second), plus the first and last frame;
  - grading renders only during the replay that records the video.
- **Correctness:**
  - CPU families replay bit-exactly. Since v17 (cloth, lock) and v18 (IPC), every family reproduces bit-exactly in
    fresh processes.
  - Settings changes (CPU fp64, IPC substeps, K2) passed dual validation (metrics and visual checks) before they
    shipped.
  - Every in-scope oracle passes both modes on v18 (`ORACLE_FIXES_FOR_JIANWEN.md`, final status).
