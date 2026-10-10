# dextoolbench_hammer_mallet_hammer_swing_down-standard

| | |
|---|---|
| Benchmark | DexToolBench |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `dextoolbench_hammer_mallet_hammer_swing_down-privileged` |
| Simulator / robot | `mujoco` / `kuka-iiwa14-sharpa-ha4` |
| Family / instance | `dextoolbench/hammer/mallet_hammer/swing_down` / seed 0 |
| Oracle | `partial` — SimToolReal's pretrained policy, replayed in this scene, reaches 12/36 goals (solution/; README of dextoolbench_hammer_mallet_hammer_swing_down-privileged) |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-mujoco:0.1.2` |

## Task
Standard-mode twin of `dextoolbench_hammer_mallet_hammer_swing_down-privileged` (see its README): the same scene, instance and scoring, served as a robot service (`images/mujoco/limited/server_mj.py`, protocol eai-standard/2.1, tooling `rcb_dtb`). The agent sees camera RGB-D and proprioception only.

## Difficulty
Same scene, instance and success rule as `dextoolbench_hammer_mallet_hammer_swing_down-privileged` (see its Difficulty). In standard mode the agent loses resets, privileged state and planning primitives: it sees camera images and proprioception only, acts through the client, and gets one episode, so it has to estimate the scene from images and recover from its own mistakes without starting over.

## Reference solution
`solution/`: the privileged-mode oracle's recorded targets submitted through the client (one row per control step)

## Verification
the sidecar replays the recorded episode in a fresh simulator; `deterministic` = same final state as the live episode

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 1.5 GB | 1.5 GB |

- GPU: required, any NVIDIA GPU; recommended: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).
- Measured: GPU 0.3-0.9 GB on 24 GB cards, vram_profile (batch_eval_live per-trial GPU peaks, 10-03..10); memory: sim p90 0.9 GB, privileged container p90 4.4 GB, mem_guard (docker memory per container, ws-1, 10-02..10); CPU author estimate
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 9 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 7 GiB GPU memory, 14 GiB memory. Limits measured: GPU: 2.1 GiB on a 48 GB card (batch_eval_live vram_profile (per-trial GPU peaks by card, 10-03..10)) -> max(1.5 x peak, peak + 4); memory: agent container docker peak 4.4 GiB over 7 samples (mem_guard (docker memory incl. page cache, top-4 containers every 10 min, ws-1, 10-02..10)) -> max(1.5 x peak, peak + 4, 8), at most the 16 GiB cap; whole trial: + the sim service's 5 GiB (docker peak 0.9 GiB, 7 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details

### Change Log
- 2026-10-10 (review 0067): the camera calibration in `meta["cameras"]` now gives the pose of the viewpoint the image is rendered from. Before, `cam2world_gl` held the position of MuJoCo's left-eye camera, 3.4 cm to the side of it, so points back-projected from depth were off by that much. This changes what the agent observes: standard-mode results from before this date are not strictly comparable.
- 2026-10-10 (review 0067): a malformed request (`dt`, `seconds` or `video_fps` not a finite number, `cameras` not a list of names, actions that are not a numeric array) is answered 400 before any physics; before, some of them (e.g. `dt = Infinity`) were a 500 that ended the episode. `meta["time_left_s"]` counts from the agent's first request, not from the service's start. `final.json` is finalized as soon as the verdict is in it (the video is rendered after it and cannot delay or void it); a missing, unreadable or verdict-less `final.json` is graded `infra_error = 1`, never a plain 0; the collect hook's wait fits inside its timeout.
- 2026-10-10 (review round 2, board 0067): crash recovery only. A service killed inside the call that ended the episode (after the end was logged, before the call's own record) resumed in the state before that call but kept the episode ended, so every later call was a 409 and the rolled-back state was graded (a 0 without `infra_error`); the resume now ignores an end that belongs to the lost call, and the episode continues from the last completed call, as the instruction says. An episode without a crash is unaffected.
