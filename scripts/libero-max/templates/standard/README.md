# {{name}}-standard

## Task
LIBERO-MAX case `{{case_id}}` as a robot service: a Franka Panda arm at a table, instructed **"{{instruction}}"**, on
the same frozen instance as `{{name}}-privileged`, with the same online event ({{event_words}}: {{event_detail}}, the
first time the gripper comes within {{trigger_m}} m of `{{trigger_object}}`). The simulator runs in the `sim` sidecar
(`environment/sim/server.py` on main's `rcb_service.py`); the agent only has the client: two cameras (RGB
{{image_hw}}×{{image_hw}}, depth on request, calibrated), the robot's own state, and OSC control steps in chunks. One
episode, no reset, no object poses; nothing to hand in. The agent is told that the scene may change once, not how or
when.

## Difficulty
The agent has to find the objects in the images, close the loop through the cameras with OSC deltas, notice the change
when it happens and adapt, and finish in one episode without a reset.

## Reference solution
`solution/`: the privileged oracle's {{n_actions}} control steps (recorded offline; see the twin's README) submitted
through the client; the episode ends with `reason = "success"` at the last of them.

## Verification
Graded by the live episode (docs/PROTOCOL.md H.4; owner, 2026-10-17, board 0151): the sim service ends the episode at
LIBERO's success (or at the {{std_cap}}-step technical cap, when the agent's time is up, or on a simulator error) and,
once the agent's container is stopped, writes its verdict to `/data/final.json` (`graded_by = "live"`, `replays = 0`,
the event record `event_fired` / `event_step`); `tests/grade.py` (separate sandbox, no network) grades it:
`success = live_success` (LIBERO's success check held in the live episode), with `infra_error = 1` when there is no
finalized verdict. Nothing is replayed to grade it. The frozen start is checked when the episode begins: a scene that
does not start at the instance's recorded state hash is `instance_mismatch` (`infra_error = 1`), before the agent is
served. After the verdict the collect hook replays `trajectory.npz` once in a fresh process for `replay.mp4` (and
`replay.video.json`: whether that replay ended in the live state); it can neither change nor cost the verdict
(`docs/benchmarks/libero-max.md`, "Grading (standard mode)").

## Details
| | |
|---|---|
| Actions | `ee_delta` (7, float64): OSC hand-target delta (1.0 = {{pos_scale}} m, {{rot_scale}} rad per control step) and gripper |
| Episode cap | {{std_cap}} control steps ({{robot_seconds}} s of robot time; `spec.max_control_steps`, PROTOCOL §4.5 MAY) |
| Resources | 4 CPUs, no GPU (CPU physics, OSMesa rendering); the collect hook: the verdict at once, then one video pass (up to 5,400 s for the longest episode on a busy host) |

### Change Log
- 2026-10-08: image `eai-libero-max:0.1.1` (`OPENBLAS_CORETYPE=Zen`); the instance, its start-state hash, the reference
  solution and the pass rule are unchanged, so the task keeps its name. With 0.1.0 the start state did not rebuild on
  Intel Xeon 8488C hosts (the Session refused with a hash mismatch): the OpenBLAS 0.3.18 bundled with numpy and scipy
  does not know that CPU and fell back to its generic Prescott kernels, while the instances were frozen with its Zen
  kernels (AMD 7950X). 0.1.1 pins the Zen kernels; same Python packages and sources. `scripts/libero-max/rebuild_check.sh`
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
  - The collect hook waits up to 5,400 s for the verdict (timeout 5,700 s): {{std_cap}} steps × 0.5 s on a busy host
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
{{change_log_extra}}