# roboolympics-fun-free-throw-realgrasp-i00-privileged

| | |
|---|---|
| Benchmark | RoboOlympics-Fun |
| Mode | privileged |
| Twin | `roboolympics-fun-free-throw-realgrasp-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `free_throw_realgrasp` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested by scripts/roboolympics/tests/test_free_throw_realgrasp.py: positive by injection (a real two-handed underhand swing with the ball held only by palm friction, squeeze kept on the shoulder roll, a real release by rolling both arms out at 5.0 m/s; the ball's velocity set at the release to the 58-degree shot: a real flight and ring); bank shot by injection; negatives: not released in 5 s (nop holds it 5 s), grip columns hold nothing, one palm alone drops it, a too-weak squeeze slips out, the real swing falls short, let go and taken back, ball pulled against the chest (body), the line, the semi-circle, beyond the line on a drop-in, from below, a fall. The two-palm shot is capped near 5.4 m/s by the shoulder pitch speed (9 rad/s); the ring needs about 8 m/s; human review in the pull request that adds the benchmark (PROTOCOL §2.7) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:robofunolympics-0.2.1` |

## Task
Shoot a free throw: from behind the free-throw line, shoot the basketball you hold pressed between your two palms so that it enters the basket from above. (RoboOlympics `free-throw-realgrasp`: one Unitree H1-2 on the RoboOlympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
The 0.62 kg ball has to leave the hands at about 8 m/s on a steep arc to reach a ring 3.05 m high and more than 4 m away, with a margin of a few centimetres in air that slows it; the hands can only squeeze it from the sides, so all of that speed has to be carried by the friction of two flat palms, and both have to leave it at the same instant without spinning it off line. The arms' fastest swing gives less than that, and the body only stands by an open-loop stance.

## Reference solution
None. No reference controller exists for this family yet: positive by injection (a real two-handed underhand swing with the ball held only by palm friction, squeeze kept on the shoulder roll, a real release by rolling both arms out at 5.0 m/s; the ball's velocity set at the release to the 58-degree shot: a real flight and ring); bank shot by injection; negatives: not released in 5 s (nop holds it 5 s), grip columns hold nothing, one palm alone drops it, a too-weak squeeze slips out, the real swing falls short, let go and taken back, ball pulled against the chest (body), the line, the semi-circle, beyond the line on a drop-in, from below, a fall. The two-palm shot is capped near 5.4 m/s by the shoulder pitch speed (9 rad/s); the ring needs about 8 m/s.

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in two fresh processes (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success in both
and both end in the same state. The rules: The official basket: a rigid ring of 0.45 m inner diameter (0.018 m metal), its top edge 3.05 m above the floor, its centre 0.375 m in front of a backboard 1.8 m wide and 1.05 m high whose lower edge is 2.9 m above the floor. The ball is a size-7 basketball (0.239 m across, 0.62 kg, it keeps 0.85 of its speed in a bounce on the floor); it flies in air (drag and spin lift). Your hands have no fingers and no grip: the ball starts pressed between your two flat palms and is at your disposal at the start; only the force of your arms and friction hold it, and it can slip out. A hand is the palm pad and the wrist; a hand is on the ball while it touches the ball, gaps shorter than 0.03 s included; the ball is in your hands while at least one hand is on it. The release is the moment the ball is no longer in your hands (no hand on it); the ball can be released only once: a ball that slips or drops out of your hands is released too. The free-throw line's edge nearest to you is 4.225 m from the point under the ring's centre; the free-throw semi-circle has a radius of 1.8 m round the middle of that edge. You succeed when, after the release, the ball's centre goes down through the ring's plane inside the ring and on down to one ball diameter below it. You fail if the ball has not been released within 5.0 s; if, before the release, the ball touches any part of you other than your hands; if, before the ball has touched the ring or entered the basket, any part of you touches the floor on or beyond the free-throw line's near edge or outside the semi-circle; if any part of you touches the ball more than 0.05 s after the release (it cannot be taken again); if the ball touches the floor before it is through the ring; if the ball's centre comes up through the ring from below; if you fall before the ball is through (a fall: your pelvis lower than 0.35 m above the floor, or any part of you other than your feet on the floor); or after 12 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §2.7).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: author estimate (ws-1, 2026-10-11): CPU-only MuJoCo with OSMesa rendering; one world steps 5 times faster than real time on one core and holds about 0.4 GB; the verifier runs two replays and a filmed one
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 13 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 13 GiB memory. Limits measured: author estimate: no trials yet; memory under the 16 GiB cap by the margin the monitor needs (an agent may run several worlds at once or train a controller); disk 20 GiB for downloaded tools and controllers; processes 512: design default.

## Details
| | |
|---|---|
| Category | basketball-and-rackets |
| Rule book | FIBA Official Basketball Rules 2024: Art. 2 (court), Art. 3 and the Basketball Equipment appendix (backboard, ring, size-7 ball), Art. 13 (how the ball is played: with the hands), Art. 14 (control: a player holds a live ball), Art. 16 (goal; a ball that passes through the basket from below is a violation), Art. 43 (free throws); deviations: Art. 3 (equipment): the hands are flat rubber palm pads without fingers; the ball is held only by pressing it between the two palms (friction), and it slips or drops when the arms do not press hard enough. Any shooting style is allowed (a two-handed set or push shot, an underhand two-handed shot); the ball is released when no hand touches it any more. · Art. 3 (equipment, the hand): the palm is modelled as the soft part of a hand: it absorbs the ball (a ball thrown at a still palm keeps 0.12 of its speed) instead of bouncing it like the floor (0.85); with the ball's own floor rebound on the palms a squeezed ball rattles out of them within about a second. The floor, the ring and the backboard keep the ball's rule-book rebound. · Art. 13.1.2 (the ball is played with the hands only) is read strictly: until the shot is through, the ball may touch no part of you but your hands (palm pads and wrists); holding it against the trunk, the arms or a leg is not a hold of this task. · Basketball Equipment (basket): the ring is rigid (no pressure release) and the net is only drawn: it does not slow the ball. A goal is judged at the ring: the ball's centre down through the ring's plane and on to one ball diameter below it. · Art. 43.2.3: the ball is at your disposal at the start of the episode; there is no referee, no opponent and no rebound: one throw, and touching the ball after the release ends the attempt. |
| Stages | release → through the ring |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `f24d746b734497513c4c349b346a3035499135f29898c549e3840e87ef4423a3` |
| Episode | 1200 control steps (12 s at 100 Hz) |
| Action | sim rows of 141 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/roboolympics-fun-files/, built from embodied_first_exam/roboolympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; docs/benchmarks/roboolympics.md) |
