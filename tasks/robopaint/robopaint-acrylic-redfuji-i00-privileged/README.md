# RoboPaint · acrylic stroke copy · Fine Wind, Clear Morning (after Hokusai) (privileged)

| | |
|---|---|
| Task ID | `robopaint-acrylic-redfuji-i00-privileged` |
| Benchmark | [RoboPaint](https://www.embodied-first-exam.ai/suite/robopaint/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Franka Emika Panda arm (ManiSkill PandaStick) holding a brush or pen |
| Mode | privileged |
| Instance | `robopaint_acrylic_redfuji`, seed 0 |
| Time limit | 1 h |
| Reference solution | Pipeline check only |

## Task
Copy the painting in `/app/target.png` (after Katsushika Hokusai's Fine Wind, Clear Morning (Red Fuji)) onto the main
sheet in at most 407 strokes.

## Success criteria
Graded on the main sheet's colours and paint coverage against the picture. Both are converted to CIELAB and blurred
with a Gaussian of σ = 1 mm. The sheet is first moved by the whole-pixel shift, at most 5 mm along each
axis, that gives the smallest mean colour difference over the picture's central window (a best shift on the edge of
that window counts as no shift); every measure is taken at that shift, on the overlap of the two pictures.
Success needs all of these:

- mean ΔE (CIELAB 1976) ≤ 2.0 and its 90th percentile ≤ 6.0, over the area where the sheet or
  the picture has paint (coverage ≥ 0.5), widened by about 2 mm;
- SSIM of the blurred L* channel (Gaussian windows, σ = 1.5 mm) ≥ 0.92;
- edge correlation ≥ 0.80: the correlation of the blurred L* gradient magnitudes of the sheet and the
  picture over that area;
- paint IoU ≥ 0.95: the sheet's painted area (coverage ≥ 0.5) against the exemplar's paint coverage;
- at most 407 painted contacts with the main sheet (a contact is one continuous stretch of the tip below
  the sheet's surface; it is painted when the brush was loaded at the touch-down);
- path budget: `path_mm` ≤ 51700 mm, the total length of the tip's path in all painted contacts with the
  main sheet (100 Hz physics samples);
- sweeps: contacts longer than 2.5 × the diagonal of their bounding box (the diagonal taken as at
  least 10 mm) hold at most 10 % of `path_mm`.

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
The paint engine is libmypaint 1.6.1 (ISC License, with a one-line determinism patch) with a preset of mypaint-brushes 2.0.2 (CC0-1.0). The base image also carries Spline-FRIDA (GPL-3.0), which this task does not use.
The exemplar: a painting made by this task's robot and brush, after Katsushika Hokusai's Fine Wind, Clear Morning (Red Fuji) (Wikimedia Commons `File:Fine Wind, Clear Morning by Hokusai (Shimane Art Museum).jpg`, public domain); the exemplar picture is dedicated to the public domain (CC0-1.0). No non-commercial terms apply.
