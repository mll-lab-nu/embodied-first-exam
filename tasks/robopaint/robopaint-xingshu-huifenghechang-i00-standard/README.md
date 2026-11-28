# RoboPaint · 行书 臨帖 · 惠風和暢 (standard)

| | |
|---|---|
| Task ID | `robopaint-xingshu-huifenghechang-i00-standard` |
| Benchmark | [RoboPaint](https://www.embodied-first-exam.ai/suite/robopaint/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Franka Emika Panda arm (ManiSkill PandaStick) holding a brush or pen |
| Mode | standard |
| Instance | `robopaint_xingshu_huifenghechang`, seed 0 |
| Time limit | 1 h |
| Reference solution | Pipeline check only |

## Task
Copy the characters 惠風和暢 (running script, 行书) in `/app/target.png` onto the main sheet with brush and ink, in at most 28
strokes.

## Success criteria
Graded on the main sheet's ink (pixels with ink coverage ≥ 0.5 on the sheet's 1024 × 1024 raster, 0.222 mm per
pixel) against the exemplar's ink. The sheet is first moved by the whole-pixel shift, at most 5 mm along each
axis, that gives the largest overlap of its ink with the exemplar's (a best shift on the edge of that window counts as
no shift); every measure is taken at that shift. Success needs all of these:

- IoU of the inked areas ≥ 0.80;
- boundary F-score ≥ 0.75: the harmonic mean of the share of the sheet's ink-edge pixels within 1 mm of the
  exemplar's edge and the share of the exemplar's edge pixels within 1 mm of the sheet's;
- each of the exemplar's 43 regions is at least 0.80 covered by ink;
- stray ink (ink more than 1 mm from the exemplar's ink) at most 0.04 of the exemplar's ink area;
- no colouring in: the task fails when `path_mm` > 6060 mm and also `mark_width_mm` < 1.15 mm.
  `path_mm` is the total length of the tip's path in all inked contacts with the main sheet (100 Hz physics samples);
  `mark_width_mm` is the area each contact inks on its own (coverage ≥ 0.5; where contacts overlap, each counts its
  own), summed over the contacts and divided by `path_mm`;
- at most 28 counted strokes: each inked contact is cut into marked pieces wherever the tip moves more
  than 5 mm along the sheet while its mark is narrower than 0.1 mm (the touch-down before the first and
  the lift after the last marking sample belong to no piece); a piece counts as one stroke, or as ⌈length /
  1250 mm⌉ strokes when it is longer than 1250 mm;
- sweeps: pieces longer than 12 × the diagonal of their bounding box (the diagonal taken as at least
  10 mm) hold at most 10 % of the pieces' total length.

The practice sheet is never scored.

What is graded is the live main sheet at the end of the one episode; nothing is replayed. The episode ends when the agent
sends `/finish`, when the agent's session ends (at the latest after 1 h), when the robot reaches the runaway guard
of 72,000 control steps (1 h of simulated time), or on a simulator error; there is no reset and no other step limit.
Once the agent's container is stopped, the service ends a contact still on the paper and scores the sheet as it stands,
with the same rules the privileged verifier uses. Meeting the conditions earlier in the episode does not count, and the
service never reports a score or a success while the episode runs.

An episode ended by a simulator error scores 0, and so does one ended because the service crashed repeatedly during the
agent's own calls. The scene is checked to rebuild the frozen instance (its hash) before the agent is served. A mismatch,
a missing or unreadable verdict, other repeated service crashes and a sheet the service could not score after a normal
end are infrastructure failures, not scores.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 5 GiB | 2048 | no GPU | 10 GiB |
| `sim` | 3 | 5 GiB | 1024 | 3 GiB | — |
| verifier (as `main`) | 8 | 5 GiB | no cap | no GPU | 10 GiB |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).

## License
RoboPaint (its scenes, tooling and graders) is part of this repository, MIT License. It runs on ManiSkill 3.0.1
([haosulab/ManiSkill](https://github.com/haosulab/ManiSkill) @ `a4a4f92`) and SAPIEN 3.0.3, both Apache License 2.0.
The brush model is this repository's re-implementation of the dynamic virtual brush of Wang et al. (IROS 2020). The base image also carries Spline-FRIDA (GPL-3.0), which this task does not use.
The exemplar: cropped from a public-domain scan of the Shenlong hand copy of Wang Xizhi's 蘭亭序 (Wikimedia Commons `File:神龍蘭亭序全.JPG`, PD-Art / PD-old-100-1923); notice in `NOTICE-exemplar.md`. No non-commercial terms apply.
