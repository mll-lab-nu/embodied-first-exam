# embodied-olympics-fun-balance-beam-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | privileged |
| Twin | `embodied-olympics-fun-balance-beam-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `balance_beam` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: positive by injection (the robot slid along the 10 cm beam in its tandem pose, 4 mm per step); negatives: `stand` mode (off in 1.5 s), the walking policy (off in 0.5 s), stopping short, past the end, lying on it, beside it. The tandem hold on joint targets is stable; a real walk on a 10 cm beam was not attempted; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Walk along the balance beam from the end you stand on to the other end and stand there, without anything touching the floor. (Embodied Olympics `balance-beam`: one Unitree G1 on the Embodied Olympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
The beam is 0.1 m wide and the robot's built-in stance and gait keep the feet 0.24 m apart, so neither can be used: every step is a single-leg balance on a sole 0.07 m wide, 1.25 m above the floor, for 5.0 m.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (the robot slid along the 10 cm beam in its tandem pose, 4 mm per step); negatives: `stand` mode (off in 1.5 s), the walking policy (off in 0.5 s), stopping short, past the end, lying on it, beside it. The tandem hold on joint targets is stable; a real walk on a 10 cm beam was not attempted.

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in one fresh process (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success. The rules: The beam is a competition balance beam: 5.0 m long, 0.1 m wide on top and 0.16 m deep, its top 1.25 m above the floor; it runs along +x from x = 0 to x = 5.0 m, centred on y = 0, on two supports. You must get from the end you start on to the far end on your feet. The far end is the last 0.5 m of the beam. You succeed when both feet are on the beam with every point at which they touch it inside the far end, and you then stand there for 2.0 s without a break: only your feet touch the beam, your torso is within 20.0 degrees of vertical and your pelvis moves slower than 0.35 m/s. You fail the moment any part of you touches the floor or the beam's supports (a fall from the beam), the moment any part of you other than a foot touches the beam (a fall on the beam: no hands, knees or sitting), or after 90 s. Leaving the beam with both feet (a hop) is allowed as long as you come down on it on your feet. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 16 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## Details
| | |
|---|---|
| Category | parkour-apparatus-balance |
| Rule book | FIG Apparatus Norms (Fédération Internationale de Gymnastique), women's artistic gymnastics, balance beam: length 5.00 m, width of the top 0.10 m, depth of the beam body 0.16 m, top 1.25 m above the floor; FIG Code of Points, women's artistic gymnastics: a beam exercise lasts at most 1 min 30 s; deviations: FIG Apparatus Norms, balance beam (padding): the beam is rigid with a friction coefficient of 1.0, without the norm's thin elastic padding and suede cover, because the simulator has rigid bodies only · FIG Apparatus Norms, landing mats: there are no 0.20 m mats round the beam; the floor is 1.25 m below the top, because anything touching the floor ends the attempt anyway · FIG Code of Points (a routine is scored, a fall costs 1.00): one pass along the beam is judged pass or fail, because the task is a single action; a hand or any part other than a foot on the beam counts as a fall here |
| Stages | half way → far end → stand |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `d1ddd243c9b81253d842716ba927caa57f99a6d134612ae0a95d424d882171d8` |
| Episode | 9000 control steps (90 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/embodied-olympics-fun-files/, built from embodied_first_exam/benchmarks/embodied-olympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
