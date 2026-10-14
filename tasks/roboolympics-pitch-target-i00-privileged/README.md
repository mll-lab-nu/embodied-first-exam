# roboolympics-pitch-target-i00-privileged

| | |
|---|---|
| Benchmark | RoboOlympics |
| Mode | privileged |
| Twin | `roboolympics-pitch-target-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `pitch_target` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_pitch_target.py: positive by injection (a real stand on the mound and release, the ball's velocity set to 22 m/s: a strike; a 14.5 m/s lob at 29 degrees is a strike too); negatives: no foot on the plate, a bounce, high, wide, touched after the release. An arm swing of the H1-2 gives 6.8 m/s, 9.9 m/s with the trunk (and a fall); human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.0` |

## Task
Pitch a strike: from the pitcher's plate on the mound, with a foot on the plate, throw the baseball in your right hand through the strike zone over home plate, on the fly. (RoboOlympics `pitch-target`: one Unitree H1-2 on the RoboOlympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
From 18.44 m the ball needs more than 13 m/s even on a high arc, and the zone is 0.43 m wide: a release direction right to about one degree. The H1-2 has no throwing motion; the speed has to come from the trunk and the whole arm while a foot stays on the plate and the body on the mound.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (a real stand on the mound and release, the ball's velocity set to 22 m/s: a strike; a 14.5 m/s lob at 29 degrees is a strike too); negatives: no foot on the plate, a bounce, high, wide, touched after the release. An arm swing of the H1-2 gives 6.8 m/s, 9.9 m/s with the trunk (and a fall).

## Verification
`tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: The baseball (0.073 m across, 0.145 kg, it flies in air with drag and spin lift) starts gripped in your right hand. You stand on the pitcher's plate (a slab 0.61 m wide and 0.152 m deep, level with the mound's top) on a mound 5.486 m across whose top is 0.254 m above home plate; in front of the plate the mound falls 1 in 12. The front edge of the pitcher's plate is 18.44 m from the back point of home plate; home plate is 0.432 m wide and as deep, so its front edge is that much nearer. The strike zone is the rectangle above home plate's front edge, 0.432 m wide and from 0.46 m to 1.07 m above home plate. The pitch: you let go of the ball (once: it cannot be gripped again) within 15.0 s of the start, and at that moment at least one of your feet is in contact with the pitcher's plate (it touches the mound and part of its sole is over the plate). You succeed when the ball's centre then crosses the plane of the zone inside the zone, before the ball has touched the ground. You fail if no foot is on the plate at the release; if the ball is not let go in time; if it touches the ground (the mound included) before home plate; if it crosses the plane outside the zone (a ball); if any part of you touches it after the release (your throwing arm may still brush it during the first 0.2 s); if you fall before the call (your pelvis lower than 0.75 m above home plate's level, or any part of you other than your feet on the ground or the mound); or after 20 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: author estimate (ws-1, 2026-10-11): CPU-only MuJoCo with OSMesa rendering; one world steps 5 times faster than real time on one core and holds about 0.4 GB; the verifier runs two replays and a filmed one
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 13 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 13 GiB memory. Limits measured: author estimate: no trials yet; memory under the 16 GiB cap by the margin the monitor needs (an agent may run several worlds at once or train a controller); disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | throwing-catching-striking |
| Rule book | Official Baseball Rules (MLB, 2024 edition): 2.01 and Appendices 1-2 (the pitcher's plate 60 ft 6 in from the back point of home plate, 10 in above it; the mound), 2.02 (home plate), 3.01 (the ball), 5.07(a) (the pivot foot in contact with the plate), 5.07(c) (the 15 s pitch timer), Definitions of Terms: "strike zone", "in flight"; deviations: 3.01: the hand holds the ball by a grip switched on and off, not by fingers (no seams: no grip-made spin beyond what the hand's motion gives); the ball is released when the grip is switched off. · Definitions (strike zone): there is no batter, so the zone's height is fixed, 0.46 m to 1.07 m above home plate (the hollow of the knee to the midpoint of the torso of a 1.8 m batter). A strike is called when the ball's centre crosses the zone's front plane (home plate's front edge) inside the zone, in flight; the rule's "any part of the ball through any part of the zone" (the plate's whole depth, the ball's edge) is not used: stricter. · 5.07(a): "the pivot foot in contact with the plate" is judged at the release: a foot that touches the mound and whose sole is over the plate; either foot may be the pivot foot. Wind-up and set positions and balks are not judged (no runners). · 5.07(c): the pitch timer runs from the start of the episode: the ball must be let go within 15.0 s. · No batter, catcher or umpire: a backstop behind home plate; one pitch, and a fall before the call ends the attempt as a failure. · Flight: quasi-steady aerodynamics (MuJoCo's ellipsoid fluid model: drag and Magnus lift), still air. |
| Stages | release → strike |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `8b6f35e26bfddacac63aed51292c6f801dd0fa48fbdc68480e0491b1a3db970d` |
| Episode | 2000 control steps (20 s at 100 Hz) |
| Action | sim rows of 141 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `environment/rcb_rfo.py`, `environment/rfo/` (the world, the action layer, the referee's toolkit) and `environment/rfo_task.py` (this family's rules), the same files as in `tests/` (scripts/roboolympics/shared/) |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
