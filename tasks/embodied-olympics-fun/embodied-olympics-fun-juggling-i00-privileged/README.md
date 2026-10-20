# embodied-olympics-fun-juggling-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | privileged |
| Twin | `embodied-olympics-fun-juggling-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `juggling` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: positive by injection (a real release, then ten real head contacts with the ball sent up again at 2.6 m/s each time); negatives: passive bouncing (one counted touch), nine then the ground, rises too small, a handball, the trunk, carried, a re-grip. Nothing built in stands on one leg; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Juggle the football: drop it from your hand and keep it in the air for ten touches in a row with your feet, legs or head, without it touching the ground or a hand again. (Embodied Olympics `juggling`: one Unitree G1 on the Embodied Olympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
Each touch is an upward strike by a leg or the head, timed to a falling 0.43 kg ball and aimed so that the ball comes down within reach again, ten times in a row; the robot has to stand on one leg to use a foot or a thigh, which neither built-in gait does, and a ball that merely bounces on a still limb loses a quarter of its height each time and wanders off.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (a real release, then ten real head contacts with the ball sent up again at 2.6 m/s each time); negatives: passive bouncing (one counted touch), nine then the ground, rises too small, a handball, the trunk, carried, a re-grip. Nothing built in stands on one leg.

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: A size-5 football (0.22 m across, 0.43 kg, in air) starts gripped in your right hand. The drop is the moment no hand grips it any more; a hand or an arm may still be in contact with the ball for 0.15 s after that (the ball leaving the hand), and the ball cannot be gripped again. From the drop on, a touch is a contact of the ball with a foot, a shin, a thigh or your head (contacts less than 0.05 s apart are one touch); it counts when the ball's centre has then risen at least 0.22 m above the height it had when the touch began, before anything touches it again, and, for every touch after the first, when the ball leaves the touch with at least 0.95 of the speed it had when the touch began (both taken at the height where the touch began; a ball that only bounces on a still limb leaves slower: such a touch is not counted, and is not a fault). You succeed at the moment the tenth touch counts. You fail if the ball touches the ground, if a hand or an arm touches it later than 0.15 s after the drop, if your trunk (chest, shoulders, pelvis) touches it, if one touch lasts longer than 0.15 s (the ball resting or balanced on you), if the ball is touched again before it has risen 0.22 m, if you fall (your pelvis lower than 0.35 m above the ground, or any part of you other than the feet on the ground; standing on one foot is not a fall), or after 30 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: author estimate (an RTX 4090 workstation, 2026-10-11): CPU-only MuJoCo with OSMesa rendering; one world steps 5 times faster than real time on one core and holds about 0.4 GB; the verifier runs two replays and a filmed one
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 13 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 13 GiB memory. Limits measured: author estimate: no trials yet; memory under the 16 GiB cap by the margin the monitor needs (an agent may run several worlds at once or train a controller); disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | football-and-volleyball |
| Rule book | Keepie-uppie (ball juggling), the football skill: the ball is dropped from the hands and kept in the air with the feet, the legs and the head, each touch counted, the count ending when the ball touches the ground or a hand; it is a skill test, not an event of the Laws, and the family's standard is 10 consecutive touches. IFAB Laws of the Game 2025/26 for the ball (Law 2: size 5, 68-70 cm round, 410-450 g) and for handling (Law 12: the hand or the arm); deviations: A counter's eye is replaced by numbers: contacts less than 0.05 s apart are one touch, a touch may last at most 0.15 s, and it counts when the ball's centre has then risen at least 0.22 m (one ball diameter) above where it was when the touch began, before anything touches it again; a ball that rolls or rests on a leg is not a touch. · A touch is a strike: so that a ball that merely bounces on a still limb or head is not juggling, every touch after the first must send the ball off with at least 0.95 of the speed it arrived with (a still limb returns about 0.85); a touch that does not is not counted, and is not a fault. · Only the feet, the legs (shin and thigh) and the head count and may touch the ball; the chest and the shoulders, which a human juggler may use, are not allowed, because the robot's trunk is one rigid shell. · The ball starts in the robot's right hand, held by the simulator's grip (the robot has fists, no fingers); the drop is the opening of the grip. No wind. |
| Stages | touch 1 → touch 2 → touch 3 → touch 4 → touch 5 → touch 6 → touch 7 → touch 8 → touch 9 → touch 10 |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `835b515b4d1151b792c6df38e861aef426406dae673f3444201998cf8f4d13ae` |
| Episode | 3000 control steps (30 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/embodied-olympics-fun-files/, built from embodied_first_exam/embodied-olympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
