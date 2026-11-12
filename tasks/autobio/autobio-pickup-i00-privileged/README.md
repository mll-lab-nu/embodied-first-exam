# autobio-pickup-i00-privileged

| | |
|---|---|
| Benchmark | AutoBio |
| Mode | privileged |
| Twin | `autobio-pickup-i00-standard` |
| Simulator / robot | `autobio` / `aloha-2-arm` |
| Family / instance | `pickup` / seed 0 (allowed seeds: [0, 1, 2]; PROTOCOL §2) |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:autobio-0.1.0` |

## Task
AutoBio's `pickup` (Pick up centrifuge tube), with an ALOHA arm (6 joints and a parallel gripper), fixed to the bench: Pick up the 50 mL centrifuge tube that stands in the rack. Success, at the first control step where both hold: the tube's body is above z = 0.925 m (it stands at 0.830 m, so 9.5 cm up) and the gripper's left finger (geom `1/aloha:leftfinger`) touches the tube's cap (geom `1/cap_cyl`).
On the bench: a 10-slot tube rack (2 rows of 5) with one capped 50 mL tube standing in it. The deliverable is one replayable trajectory of joint position targets (`/app/output/trajectory.npz`, `(T, 7)`, one row per 2 ms control step).

## Difficulty
AutoBio's level: easy. The tube is lifted out of its rack slot by its screw cap; the check needs the cap between the fingers while the tube is 9.5 cm up. The agent has full access to the simulator and to AutoBio's task code, but not to its scripted expert: it has to build the motion itself from joint position targets at the physics rate.

## Reference solution
AutoBio's scripted expert (pickup_centrifuge_tube.py @ 0850421), seed 0: the position targets it sends, recorded at every physics step, clipped to the actuators' ranges, rounded to float32 (so the standard twin's client executes the same rows), cut at the first success: `solution/oracle.npz`, 3945 rows, success after 3945 control steps. Replayed and saved by `solution/solve.sh`; re-checked by the privileged verifier (`harbor run -a oracle`: two fresh-process replays, same final state).

## Verification
`tests/grade.py` in a separate sandbox without network: one replay of `/app/output/trajectory.npz`, in a fresh process, from the verifier's own copy of the instance (`tests/instance.json`; the compiled model and the rebuilt start state are checked against its recorded hashes); pass iff the episode succeeds (the first control step at which AutoBio's check holds ends the episode in success). `nop`: no trajectory, reward 0.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 12 GiB | 8192 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## Details
| | |
|---|---|
| Upstream | AutoBio (github.com/autobio-bench/AutoBio @ 0850421, no licence stated: the image is built locally, images/autobio/BUILD_ONLY) on MuJoCo 3.3.0 |
| Instance | `Pickup` (`pickup_centrifuge_tube.py`) after AutoBio's `reset(seed=0)`; model hash `d3406a0e2ed85218`, start-state hash `42f230966a7b71a8`, checked on every load |
| Actions | 7 position targets per control step (2 ms, one physics step); success rule `first` (tasks/autobio/README.md) |
| Resources | 4 CPUs, no GPU (CPU physics, OSMesa rendering) |
