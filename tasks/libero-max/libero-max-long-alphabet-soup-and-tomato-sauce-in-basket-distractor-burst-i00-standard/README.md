# libero-max-long-alphabet-soup-and-tomato-sauce-in-basket-distractor-burst-i00-standard

| | |
|---|---|
| Benchmark | LIBERO-MAX |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `libero-max-long-alphabet-soup-and-tomato-sauce-in-basket-distractor-burst-i00-privileged` |
| Simulator / robot | `robosuite` / `franka-panda` |
| Family / instance | `libero-max/libero_10/distractor_burst` / seed 195 |
| Oracle | `full` |
| Agent time budget | 1800 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:libero-max-0.1.1` |

## Task
LIBERO-MAX case `pro-initial-pose-position-angle-10-t00-i01-distractor_burst-d0-p195` as a robot service: a Franka Panda arm at a table, instructed **"Put both the alphabet soup and the tomato sauce in the basket."**, on
the same frozen instance as `libero-max-long-alphabet-soup-and-tomato-sauce-in-basket-distractor-burst-i00-privileged`, with the same online event (distractor burst: 5 other objects appear on the table (`butter_1`, `ketchup_1`, `milk_1`, `cream_cheese_1`, `orange_juice_1`), the
first time the gripper comes within 0.18 m of `alphabet_soup_1`). The simulator runs in the `sim` sidecar
(`environment/sim/server.py` on main's `rcb_service.py`); the agent only has the client: two cameras (RGB
256×256, depth on request, calibrated), the robot's own state, and OSC control steps in chunks. One
episode, no reset, no object poses; nothing to hand in. The agent is told that the scene may change once, not how or
when.

## Difficulty
The agent has to find the objects in the images, close the loop through the cameras with OSC deltas, notice the change
when it happens and adapt, and finish in one episode without a reset.

## Reference solution
`solution/`: the privileged oracle's 301 control steps (recorded offline; see the twin's README) submitted
through the client; the episode ends with `reason = "success"` at the last of them.

## Verification
Graded by the live episode (docs/protocol/README.md H.4; owner, 2026-10-17): the sim service ends the episode at
LIBERO's success (or at the 9000-step technical cap, when the agent's time is up, or on a simulator error) and,
once the agent's container is stopped, writes its verdict to `/data/final.json` (`graded_by = "live"`, `replays = 0`,
the event record `event_fired` / `event_step`); `tests/grade.py` (separate sandbox, no network) grades it:
`success = live_success` (LIBERO's success check held in the live episode), with `infra_error = 1` when there is no
finalized verdict. Nothing is replayed to grade it. The frozen start is checked when the episode begins: a scene that
does not start at the instance's recorded state hash is `instance_mismatch` (`infra_error = 1`), before the agent is
served. After the verdict the collect hook replays `trajectory.npz` once in a fresh process for `replay.mp4` (and
`replay.video.json`: whether that replay ended in the live state); it can neither change nor cost the verdict
(`tasks/libero-max/README.md`, "Grading (standard mode)").

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 5 GB | 4 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: verifier 1.6 GB, mem_guard (docker memory per container, an RTX 4090 workstation, 10-02..10); the rest author estimate (robosuite, CPU-only, 256x256 OSMesa cameras)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 17 GiB memory. Limits measured: memory: no samples of the agent's container; floor 8 GiB (at most the 8 GiB cap); whole trial: + the sim service's 9 GiB (from the minimum: no samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Actions | `ee_delta` (7, float64): OSC hand-target delta (1.0 = 0.05 m, 0.5 rad per control step) and gripper |
| Episode cap | 9000 control steps (450 s of robot time; `spec.max_control_steps`, PROTOCOL §4.5 MAY) |
| Resources | 4 CPUs, no GPU (CPU physics, OSMesa rendering); the collect hook: the verdict at once, then one video pass (up to 5,400 s for the longest episode on a busy host) |

### Change Log
- 2026-10-08: image `efe:libero-max-0.1.1` (`OPENBLAS_CORETYPE=Zen`); the instance, its start-state hash, the reference
  solution and the pass rule are unchanged, so the task keeps its name. With 0.1.0 the start state did not rebuild on
  Intel Xeon 8488C hosts (the Session refused with a hash mismatch): the OpenBLAS 0.3.18 bundled with numpy and scipy
  does not know that CPU and fell back to its generic Prescott kernels, while the instances were frozen with its Zen
  kernels (AMD 7950X). 0.1.1 pins the Zen kernels; same Python packages and sources. The rebuild check
  (start-state hash and reference replay of all 64 instances): 8488C 0/64 with 0.1.0, 64/64 with 0.1.1; 7950X 64/64.
- 2026-10-10: the replay video can no longer cost a verdict (`environment/sim/lmx_tool.py`, `server.py`, `finalize.sh`);
  the instance, the reference solution and the pass rule are unchanged, so the task keeps its name.
  - Before: the grading replay printed its verdict only after encoding the video, so an encoder failure threw the verdict
    away and the whole episode was replayed again; and the video's frames were rendered inside a wait sized without
    them (3,000 s), so a long live success on a busy host could end without a replay verdict (`infra_error = 1`).
  - Now: the verdict is in `final.json` the moment the replay has executed the last action; the final frame and the
    encoder's flush come after it; a video failure only means `video = false`, never a second replay. The video's
    cost before the verdict is capped at 240 s (one frame per `replay_video_stride` control steps: 2 up to 2,400
    steps, a time-lapse of at most 1,200 frames beyond; frames are skipped when the host is slower than that).
  - The collect hook waits up to 5,400 s for the verdict (timeout 5,700 s): 9000 steps × 0.5 s on a busy host
    + 180 s to build the scene + 240 s of video = 4,920 s.
  - `tests/grade.py` writes every `reward.json` field (`deterministic` among them) also when `final.json` is missing or
    unreadable; the verdict rule is the same.
  - Checked with a stubbed simulator (encoder, render and disk failures, a crash and a hang after the verdict, the
    budget) and one reference replay in the real simulator (same final state hash with the video as without).
- 2026-10-10 (2): the sim service (`environment/sim/rcb_service.py`) refuses a negative `Content-Length` unread (400; it
  read until the client hung up). Nothing else changes; the task keeps its name.
- 2026-10-10 (3; third review round): the sim service (`environment/sim/rcb_service.py`) renders and returns a camera
  named more than once in `cameras` once (N copies of one name made it build N x N images within the frame budget,
  which could exhaust its memory), and a service that has given up on the episode (it could not resume it after its
  crashes) answers every request with 409 and the reason instead of not listening. A simulator that fails inside `POST
  /reset` ends the episode as `error` (`sim_error = 1`), not `reset` (reachable only when a run grants resets; the
  default is none). The scene, instance, pass rule and every verdict reached before are unchanged, so the task keeps
  its name.
- 2026-10-14: the instruction says that a moved object or receptacle jumps alone: what rests in or on it stays where it was (LIBERO-MAX moves one entity; a review saw a basket jump through a can already in it). Text only: the instance, the event, the reference solution, LIBERO's success check and the verifier are unchanged, so the task keeps its name.
- 2026-10-16: the collect hook waits for the replay (and its video) of an episode that ended without a live success as long as for any other (`RCB_FAIL_WAIT_S` 900 -> 5400 s, the overall wait): it stopped at 900 s, so most failed episodes had no `replay.mp4`. Video only: a failure is graded 0 whatever its replay says, so the verdict, the physics and the pass rule are unchanged and results from before this date stay valid.
- 2026-10-17 (owner): graded by the live episode, no grading replay. `success = live_success`: LIBERO's success check held in the episode the sim service ran (it ends the episode the moment the check holds; the replay applied no other rule, so the rule is unchanged); `final.json` has `graded_by = "live"`, `replays = 0` and the live event record (`event_fired`, `event_step`); `replay_success`, `deterministic` and the replay's event fields are gone, from `reward.json` too (`graded_by_live`, `replays`, `instance_mismatch`, `event_fired`, `event_step` added). The frozen start is checked when the episode begins (the instance's start-state hash; a mismatch is `instance_mismatch`, `infra_error = 1`), no longer only when a replay rebuilt it. Video by one video-only replay of `trajectory.npz` in a fresh process after the verdict (`replay.video.json` says whether it ended in the live state); a failed or slow video costs only the video. The collect hook stops at 5,400 s overall as before (`RCB_FAIL_WAIT_S`, `RCB_VIDEO_GRACE_S` gone). The instance, the event, the reference solution and the agent's interface are unchanged, so the task keeps its name.
