# RoboPaint · oil painting from a reference · Wanderer above the Sea of Fog (after Friedrich) (standard)

| | |
|---|---|
| Task ID | `robopaint-oil-wanderer-i01-standard` |
| Benchmark | [RoboPaint](https://www.embodied-first-exam.ai/suite/robopaint/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Franka Emika Panda arm (ManiSkill PandaStick) holding a brush or pen |
| Mode | standard |
| Instance | `robopaint_oil_wanderer`, seed 0 |
| Time limit | 1 h |
| Reference solution | Pipeline check only |

## Task
Paint the picture in `/app/target.png` (a square crop of Caspar David Friedrich's Wanderer above the Sea of Fog) onto
the main sheet with the oil paints, in at most 1974 strokes.

## Success criteria
Graded on the main sheet's colours and paint coverage against the picture. Both are converted to CIELAB and blurred
with a Gaussian of σ = 1 mm. The sheet is first moved by the whole-pixel shift, at most 5 mm along each
axis, that gives the smallest mean colour difference over the picture's central window (a best shift on the edge of
that window counts as no shift); every measure is taken at that shift, on the overlap of the two pictures, inside the part of the sheet at least 8 mm in from its edges.
Success needs all of these:

- mean ΔE (CIELAB 1976) ≤ 3.1 and its 90th percentile ≤ 5.5, over the area where the sheet or
  the picture has paint (coverage ≥ 0.5), widened by about 2 mm;
- SSIM of the blurred L* channel (Gaussian windows, σ = 1.5 mm) ≥ 0.87;
- edge correlation ≥ 0.78: the correlation of the blurred L* gradient magnitudes of the sheet and the
  picture over that area;
- paint IoU ≥ 0.96: the sheet's painted area (coverage ≥ 0.5) against the exemplar's paint coverage;
- at most 1974 painted contacts with the main sheet (a contact is one continuous stretch of the tip below
  the sheet's surface; it is painted when the brush was loaded at the touch-down);
- path budget: `path_mm` ≤ 64700 mm, the total length of the tip's path in all painted contacts with the
  main sheet (100 Hz physics samples);
- sweeps: contacts longer than 2.5 × the diagonal of their bounding box (the diagonal taken as at
  least 10 mm) hold at most 10 % of `path_mm`.

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
The paint engine is libmypaint 1.6.1 (ISC License, with a one-line determinism patch) with a preset of mypaint-brushes 2.0.2 (CC0-1.0). The base image also carries Spline-FRIDA (GPL-3.0), which this task does not use.
The exemplar: a square crop of Caspar David Friedrich's Wanderer above the Sea of Fog (Wikimedia Commons `File:Caspar David Friedrich - Wanderer above the sea of fog.jpg`, public domain), downscaled to the sheet. No non-commercial terms apply.
