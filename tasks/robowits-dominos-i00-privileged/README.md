# robowits-dominos-i00-privileged

| | |
|---|---|
| Benchmark | RoboWits |
| Mode | privileged |
| Twin | `robowits-dominos-i00-standard` |
| Simulator / robot | `robowits` / `marvin-bimanual` |
| Family / instance | `dominos` / seed 0 |
| Oracle | `partial` — Reference solution solution/oracle_dominos.py (written for this instance; RoboWits ships no expert). It scored 1 under Harbor -a oracle on an earlier version of this task: job robowits-dominos-i00-oracle-thin-0925-000706, trial robowits-dominos-i00__qL9Rvsb, 2026-09-25 (laptop, Intel; success=1, deterministic=1, instance_exact=1; an uncommitted tree just before dev/qineng f15dbdb7). Same since then: the frozen instance (state hash 4f933a76ce2ce34b) and the oracle script (byte-identical to that run's /app/output/gen.py). Changed since then, so the label is partial: the grader tests/grade.py (dev/qineng 82d76c61 added the GPU-backend exception; this PR writes the verdict before the video) and the tooling rcb_robowits.py (dev/qineng 5aa848bd, bddfc520, adce3fef, 8f0ebd55, 82d76c61, 6c0b439e, fe5fb9e6, 1515ea4e). Not re-run on this version (static validation only, 2026-10-01). |
| Agent time budget | 5400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robowits:0.1.1` |

## Task
Push the red block onto the green target area. One replayable trajectory from the frozen instance (evaluation scene 0
of RoboWits task 6), with the privileged tooling (`rcb_robowits.py`: the scene's state, resets, thin primitives,
replay); the success criterion as graded is in `instruction.md`.

## Difficulty
Physical reasoning rather than pick-and-place: the red block ends on the target only through a chain of collisions.
White block 3 has to be toppled along the chain direction (about 26 deg off the table's x axis in this scene) hard
enough to carry through blocks 2 and 1, and gently enough that the red block falls onto the 6 x 10 cm patch instead of
past it. Nothing can be undone within one attempt, but the agent may reset and rehearse as often as it likes before
committing a trajectory.

## Reference solution
`solution/oracle_dominos.py` (RoboWits ships no expert; written for this instance): it pushes white block 3 near its
top along the chain direction with the closed right gripper, then retreats and lets the chain fall.
`solution/solve.sh` records it into a trajectory.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in a fresh process, twice; pass iff
RoboWits' `_check_success` holds after every replay, the final-state hashes agree and the rebuilt frozen scene matches
the recorded one (`tests/grade.py`; a scene that does not match is the host's failure, `infra_error = 1`, never the
agent's 0), plus `/logs/verifier/replay.mp4`. What the predicate checks, in words:
`instruction.md`, "Success criterion (as graded)". The trajectory is the per-control-step JOINT_ABS record (T, 16);
Genesis' CPU backend restores the frozen snapshot exactly, so in-process repeats and fresh processes agree bit for bit
on one CPU vendor (docs/benchmarks/robowits.md).

Oracle partial: the reference solution scored 1 on an earlier version of this task and was not re-run on this one
(`oracle_evidence` in `task.toml`); human review in PR #3 (PROTOCOL §2.7).

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 6 GB | 3 GB |
| GPU memory | 2 GB | 2 GB |

- GPU: required, any NVIDIA GPU; recommended: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).
- Measured: GPU 0.5-1.4 GB (physics on the CPU, GPU renders the cameras), vram_profile (batch_eval_live per-trial GPU peaks, 10-03..10); memory: sim p90 4.5 GB, privileged container p90 4.7 GB, verifier 2.4 GB, mem_guard (docker memory per container, ws-1, 10-02..10); CPU author estimate (single-threaded Genesis CPU backend)
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: 6 GiB GPU memory, 16 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 6 GiB GPU memory, 16 GiB memory. Limits measured: GPU: 1.4 GiB (batch_eval_live vram_profile (per-trial GPU peaks by card, 10-03..10)) -> max(1.5 x peak, peak + 4); memory: the [environment] cap 16 GiB, which every past trial ran under (docker peak 5.1 GiB over 10 samples, mem_guard (docker memory incl. page cache, top-4 containers every 10 min, ws-1, 10-02..10)); processes 512 and disk 10 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| RoboWits task | `06-dominos-v0` (RoboWits @ 9cc30ae, Genesis 0.4.7: CPU physics backend, EGL rendering on the GPU) |
| Instance | entry 0 of RoboWits' `eval_dataset_50/06.json`; object poses and the expected state hash in `environment/instance.json` (the verifier's copy in `tests/`) |
| Robot | Marvin bimanual: 2 × 7-DoF arms with Pika parallel grippers; JOINT_ABS actions (T, 16) at 30 Hz |
| GPU | EGL camera rendering only (`environment/docker-compose.yaml`, `tests/docker-compose.yaml`) |

### Change Log
- 2026-10-10 (review of board 0067; findings RW-1, RW-5, RW-6, RW-7): the verifier reports an infrastructure error (`infra_error = 1`) instead of the agent's 0 when it cannot build the frozen scene or the scene it rebuilt does not match the frozen instance on its host (`instance_ok = 0`: another CPU vendor, docs/benchmarks/robowits.md, Hosts); a `trajectory.npz` that cannot be read or lacks `task` / `actions` is `bad_trajectory`, no longer `grader_error`; `reward.json` always carries `infra_error`; the verifier runs without network (`network_mode = "no-network"`); the instruction states the tooling's cap of 200000 control steps per trajectory instead of leaving it unsaid. The pass rule, the frozen instance, the tooling and the predicate are unchanged; validated with synthetic tests of the grader, not re-run in the simulator.
- 2026-10-10 (review round 2, board 0067; minor 2): `tests/grade.py` time-boxes the replay video, which it renders after the verdict is on disk: it is skipped or stopped (`video_timed_out = 1`) 180 s before the verifier's `timeout_sec` (`tests/test.sh` passes it as `--budget`). Before, the video replay of a very long trajectory could run into Harbor's verifier timeout, which discards the verdict already written. The verdict, the pass rule, the frozen instance and the tooling are unchanged; validated with a synthetic test of the grader, not re-run in the simulator.
- 2026-10-10 (owner decision, board 0072): the agent's network egress is restricted to the model APIs (`[agent] network_mode = "allowlist"`, the hosts of `scripts/set_agent_egress.py`; since 2026-10-11 these include the package registries, PyPI and the Debian / Ubuntu archives, so that `pip install` and `apt-get install` work); it was open before (Harbor's default), and agents could download upstream sources, reference solutions and robot models from their own shell. The scene, the frozen instance, the tooling and the pass rule are unchanged, so the task keeps its name; results from before this date were obtained with open egress.
