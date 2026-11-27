# RoboPaint · lettering · Liberty. (privileged)

| | |
|---|---|
| Task ID | `robopaint-lettering-liberty-i00-privileged` |
| Benchmark | [RoboPaint](https://www.embodied-first-exam.ai/suite/robopaint/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Franka Emika Panda arm (ManiSkill PandaStick) holding a brush or pen |
| Mode | privileged |
| Instance | `robopaint_lettering_liberty`, seed 0 |
| Time limit | 1 h |
| Reference solution | Pipeline check only |

## Task
Copy the flourished word "Liberty." (English round hand) in `/app/target.png` onto the main sheet with pen and ink, in
at most 5 strokes.

## Success criteria
Graded on the main sheet's ink (pixels with ink coverage ≥ 0.5 on the sheet's 1024 × 1024 raster, 0.222 mm per
pixel) against the exemplar's ink. The sheet is first moved by the whole-pixel shift, at most 5 mm along each
axis, that gives the largest overlap of its ink with the exemplar's (a best shift on the edge of that window counts as
no shift); every measure is taken at that shift. Success needs all of these:

- IoU of the inked areas ≥ 0.85;
- boundary F-score ≥ 0.80: the harmonic mean of the share of the sheet's ink-edge pixels within 1 mm of the
  exemplar's edge and the share of the exemplar's edge pixels within 1 mm of the sheet's;
- each of the exemplar's 82 regions is at least 0.75 covered by ink;
- stray ink (ink more than 1 mm from the exemplar's ink) at most 0.04 of the exemplar's ink area;
- at most 5 inked contacts with the main sheet (a contact is one continuous stretch of the tip below the
  sheet's surface; it is inked when the pen was loaded at the touch-down);
- no colouring in: the task fails when `path_mm` > 7940 mm and also `mark_width_mm` < 0.13 mm.
  `path_mm` is the total length of the tip's path in all inked contacts with the main sheet (100 Hz physics samples);
  `mark_width_mm` is the area each contact inks on its own (coverage ≥ 0.5; where contacts overlap, each counts its
  own), summed over the contacts and divided by `path_mm`.

The practice sheet is never scored.

What is graded is the main sheet after one open-loop replay of the delivered trajectory. The verifier, in a separate
sandbox without network, replays `/app/output/trajectory.npz` (array `actions`, shape (T, 7): absolute joint targets,
one row per 20 Hz control step, T at most 72,000) once, in a fresh process, from its own copy of the frozen instance; a
contact still on the paper after the last row is ended there, and the sheet is then scored as above. Meeting the
conditions earlier in the replay does not count.

A missing file scores 0, and so does an invalid one: not a readable `.npz` (pickled or object arrays included), no
`actions` array, a shape other than (T, 7), a NaN or infinite value, more than 72,000 rows, or a `task` entry that names
another task. A replay that gives no result within 1650 s, or a verifier that cannot rebuild the frozen instance, is an
infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 12 GiB | 2048 | 3 GiB | 10 GiB |
| `scorer` | 2 | 4 GiB | 1024 | 3 GiB | — |
| verifier | no cap | no cap | no cap | 3 GiB | no cap |

- GPU: any NVIDIA GPU, held by `main` and `scorer`.
- Recommended GPU: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).

## License
RoboPaint (its scenes, tooling and graders) is part of this repository, MIT License. It runs on ManiSkill 3.0.1
([haosulab/ManiSkill](https://github.com/haosulab/ManiSkill) @ `a4a4f92`) and SAPIEN 3.0.3, both Apache License 2.0.
The pointed-pen model is this repository's own. The base image also carries Spline-FRIDA (GPL-3.0), which this task does not use.
The exemplar: re-drawn with this task's pen from George Bickham, *The Universal Penman* (London, 1741), public domain (scan: Internet Archive `gri_33125008538056`, NOT_IN_COPYRIGHT); notice in `NOTICE-exemplar.md`. No non-commercial terms apply.
