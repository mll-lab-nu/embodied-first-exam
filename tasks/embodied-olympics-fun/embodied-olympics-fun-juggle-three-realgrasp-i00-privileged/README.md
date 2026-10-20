# embodied-olympics-fun-juggle-three-realgrasp-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | privileged |
| Twin | `embodied-olympics-fun-juggle-three-realgrasp-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `juggle_three_realgrasp` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: positive: throws injected (jaws opened by command, ball put on an arc to the other jaws), all 10 catches real (the ball falls between the open jaws pointing up; the jaws close at 5 cm and the pads clamp for 0.05 s). Negatives: back into / clamped by its own gripper, low pass, never closes, closes too early (ball on the tips), waiting ball pushed, onto the head, held ball pressed on the upper arm, weak clamp slips (jaws 33 deg down: 3.3 N holds, ~1.5 N falls), a fall; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Juggle three balls in a cascade: throw each ball from one gripper in an arc to the other, the hands in turn, catching each between the jaws, until 10 catches have been made in a row. (Embodied Olympics `juggle-three-realgrasp`: one Unitree G1 on the Embodied Olympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
Each throw has to come down between jaws that leave 10 mm on each side of the ball, 0.4 m away, about 0.6 s later, the jaws must close on it within a few hundredths of a second before it bounces off, and the catching gripper must have thrown its own ball before: three balls, two hands, never two in one. A throw is the gripper opening while the arm moves, and errors add up from throw to throw, because a ball is thrown from wherever it was caught.

## Reference solution
None. No reference controller exists for this family yet: positive: throws injected (jaws opened by command, ball put on an arc to the other jaws), all 10 catches real (the ball falls between the open jaws pointing up; the jaws close at 5 cm and the pads clamp for 0.05 s). Negatives: back into / clamped by its own gripper, low pass, never closes, closes too early (ball on the tips), waiting ball pushed, onto the head, held ball pressed on the upper arm, weak clamp slips (jaws 33 deg down: 3.3 N holds, ~1.5 N falls), a fall.

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: Three balls (0.07 m across, 0.13 kg). Both your hands are two-jaw grippers (90 mm stroke, jaws 80 mm long with rubber pads on their inner faces, at most 120 N of grip) that hold things only by friction. At the start your forearms point forwards and your grippers' jaws point up; the blue ball is held between the jaws of your left gripper, the yellow ball between those of your right gripper, and the red ball waits 0.16 m above the centre of your right gripper's jaws: it stands for the second ball of the right hand and is thrown for you at t = 2.0 s, on an arc that rises 0.5 m and comes down on where the centre of your left gripper's jaws is at the start. Before that it may not be touched (by you or by a ball you hold). A catch: the pads of both jaws of a gripper press on a ball from its two sides (each with a contact whose direction is within 45.0 degrees of the jaws' closing direction: a ball lying on the jaws' tips or edges is not caught) for 0.05 s without a break, on a ball that has been thrown by the other hand (the red ball's first throw counts as the right hand's), the clamp beginning at the latest 0.15 s after the ball first touched you again. A ball is in a hand from its catch (the blue and the yellow ball from the start) until it has touched nothing of that gripper for 0.02 s: its release, at its last contact with the gripper; a ball in a hand may touch nothing of you but that gripper. A throw: after the release the ball, touching nothing but air, rises at least 0.3 m above the point where it left the gripper; only the rise before the ball first touches you again counts. The cascade's order: the catches alternate between the hands, the left hand first, and take the balls in the order red, blue, yellow, red, ... You succeed at the 10th catch. You fail if a ball touches the ground; if a ball in a hand touches any part of you other than that gripper (the other gripper included); if a ball in flight touches any part of you other than a gripper, or still touches the gripper that released it later than 0.1 s after the release; if a ball is caught by the gripper that released it, or before it has risen 0.3 m; if a ball that has touched a gripper again is not clamped within 0.15 s (it rests on the gripper or bounces off it); if a catch is out of the cascade's order (the wrong hand or the wrong ball); if the waiting ball is touched before its launch; if you fall (your pelvis lower than 0.35 m above the ground, or any part of you other than your feet on the ground); or after 20 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

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
| Category | throwing-catching-striking |
| Rule book | No rule book: the three-ball cascade as jugglers define and count it (siteswap 3; the International Jugglers' Association counts a run in catches): each ball is thrown from one hand and caught by the other, the hands throw in turn, the balls follow one another in a fixed order; a run ends with a drop; deviations: The hands are Unitree's Dex1-1 two-jaw grippers (90 mm stroke, jaws 80 mm long and 34 mm wide with rubber pads, at most 120 N of grip, opening and closing at most 375 mm/s); nothing is welded. A gripper holds one ball between its jaws, so "two balls in one hand at the start" is modelled: the first of the two (the red ball) waits 0.16 m above the right gripper's jaw centre and is thrown by the venue at t = 2.0 s, on an arc that rises 0.5 m and comes down on where the left gripper's jaw centre is at the start. Until then it may not be touched. · A catch is the pads of both jaws of the catching gripper pressing on the ball from its two sides (each with a contact within 45.0 degrees of the jaws' closing direction) for 0.05 s without a break, the clamp beginning at the latest 0.15 s after the ball first touched you again; a ball is in a hand from its catch until it has touched nothing of that gripper for 0.02 s (released, at its last contact: a ball that rattles in the jaws is not released), and it may touch nothing of you but that gripper. · A throw is a release after which the ball, touching nothing, rises at least 0.3 m above where it left the gripper; a hand-to-hand pass is not a throw. So that a ball laid on the other hand and lifted is not one, the rise counts only until the ball first touches you again. · The balls are spheres of a juggling ball's size and mass with a soft bounce; they fly in air (MuJoCo's ellipsoid fluid model: drag, a quasi-steady model), still air. |
| Stages | first catch → half way → ten catches |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `d703b787eeda4566dbc29ad31682b324c97f082d0f292c0e7a034861a03cc545` |
| Episode | 2000 control steps (20 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/embodied-olympics-fun-files/, built from embodied_first_exam/embodied-olympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
