# MetaWorld+

All fifty of [Meta-World](https://github.com/Farama-Foundation/Metaworld)'s v3 environments (Sawyer arm, reward v2),
each on one frozen instance, in both modes: 100 tasks.

## Quick start
```bash
harbor run -d embodied-first-exam@all -p tasks/metaworldplus -a codex -m openai/gpt-6-astra
```
Every image is public: Harbor pulls it.

| | |
|---|---|
| upstream | Meta-World @ `59fc34d7768af9785e4688c3e1db671424f4a6c3` (MIT), MuJoCo 3.3.0, gymnasium 1.1.1 |
| tasks | `tasks/metaworldplus/metaworldplus-<env>-i00-privileged` and `tasks/metaworldplus/metaworldplus-<env>-i00-standard` (twins share the instance) |
| metadata | `simulator = "mujoco"`, `robot = "sawyer"`, `family = "metaworld/<env>"`, `oracle = "full"` |
| image | `ghcr.io/mll-lab-nu/efe:metaworld-0.1.0` (`images/metaworld/`), CPU only |
| standard client | the one client base and pins of `embodied_first_exam/standard/` (`client.env`, `client-requirements.txt`); `rcb_client.py` / `rcb1.py` byte copies of the MuJoCo standard tasks' (accepting both protocol spellings) |
| instances | each instance and oracle is committed in its privileged task (`environment/instance.npz`, `solution/oracle.npz`). The task directories are the deliverable; the tooling that built them is kept outside this repository. |

## Task definition
- **Instance.** Meta-World's reset randomization (object and goal positions) drawn with the instance seed: 0, except
  soccer and stick-pull (1), where Meta-World's scripted policy fails on seed 0. Frozen in `instance.npz` (~13 KB): the
  MuJoCo integration state, the model arrays reset rewrites, the env's JSON-encodable caches and both RNG states,
  with a SHA-256 checked on every load. Copied into `environment/`, `tests/` and `environment/sim/`.
- **Actions.** Meta-World's native action in both modes, `[dx, dy, dz, grip]` clipped to [-1, 1], one per control step
  (0.0125 s = timestep 0.0025 s × frame_skip 5): the hand's mocap target moves by `[dx, dy, dz]` × 1 cm and the arm
  follows through a weld; `grip` drives the fingers. There is no `joint_position` action (PROTOCOL §4.4 SHOULD): the
  Sawyer in Meta-World has no arm actuators (`model.nu = 2`, the two fingers), so joint targets would mean changing
  the upstream robot model. In standard mode the type is called `ee_delta`.
- **Success.** Meta-World's own check (`evaluate_state`) on the state after the last action (PROTOCOL §3): no
  "success at any step". The check differs per environment, and a standard-mode agent cannot read the source, so both
  instructions state it in words (one sentence per environment, read from
  the source at the pinned commit): what is compared with the target point, in which axes, with which tolerance, and
  whatever else the final state must satisfy. Not every check is "the object near the target": stick-push also needs
  the stick still grasped and lifted, stick-pull the stick still in the thermos's handle (so letting go of the stick
  after the motion loses the success); hammer is the nail driven more than 9 cm in (the hammer's position is not
  compared); lever-pull is the lever's angle; door-open, door-unlock and the two window tasks compare x only, the
  button, handle-press / handle-pull and door-lock tasks one axis, disassemble the nut's height only. In three environments (handle-press, handle-pull-side, stick-pull) the success state does
  not persist by itself (holding still for 10 control steps after the oracle's last action loses it); their READMEs
  say so, and the instructions tell the agent that only the final state counts.
- **Length.** Privileged deliverables have 1 ≤ T ≤ 500 actions (Meta-World's `max_path_length`; the MuJoCo
  Playground tasks bound theirs the same way). Standard episodes have no step limit (D1): only the wall clock.
- **World frame.** Metres; x to the robot's right, y forward (away from the robot's base), z up; table top at z = 0.
  Both instructions state it; the workspace box of the hand's target is given per task.
- **Standard-mode observations.** Four fixed cameras (`front`, `left`, `right` and Meta-World's `topview`; RGB, depth,
  intrinsics and camera-to-world pose), proprioception (`tcp`, gripper opening, mocap target, arm and finger joints,
  last command) and `meta["task"]["target_pos"]`, Meta-World's `_target_pos` (as the MuJoCo Playground standard tasks
  give their target): the point most checks measure against; for hammer and lever-pull it only marks where the nail's
  head / the lever's end finishes, and the instruction says so. The calibration is the pose of the viewpoint the image
  is rendered from (not MuJoCo's left-eye camera, 3.4 cm to the side). No object poses, no reward, no success signal. Meta-World's
  per-camera views `corner*` are left out: they render upside down.

## Standard-mode service (`images/metaworld/standard/server_mw.py`)
Derived from `images/mujoco/limited/server_mj.py` and identical in protocol and lifecycle (four endpoints, RCB1, no
reset, journal + per-call checkpoints with at most two resumes, startup watchdog, SIGUSR1 collect hook, `/data`
evidence, verdict before video). Differences:
1. The action type comes from the tool module (`mw_tool.ACTION_TYPE`: `ee_delta`) instead of a fixed `joint_position`.
2. Watching (`/observe` with `seconds > 0`) holds the hand still (`S.hold_targets()`), since actions are deltas.
3. Cameras and proprioception come from the tool module (`CAMERA_VIEWS`, `PROPRIO_LAYOUT`); `meta.task` is the target.
4. DexToolBench's goal logic is gone.
5. As in the MuJoCo service: a simulator error (500) ends the episode with
   `reason = "error"`, a body over 64 MB gets 413; a request is validated in full before any physics, and a malformed
   one (`dt` / `seconds` / `video_fps` not a finite number, `cameras` not a list of names, actions that are not a
   numeric array) is a 400 that changes nothing; `final.json` carries `live_success` and the grader writes numeric
   fields only; `/status` and `meta` also carry `sim_steps`, submit responses `clipped`.

Protocol: `eai-standard/2.1` (`/spec`, `task.toml`, instructions). Every task is in the normal form of
`scripts/task_conventions.py` `normalize` (README layout, no `results/`).

## Grading (standard mode): the live episode
The standard twin is graded by the live episode and nothing is replayed to grade it (privileged mode: the verifier's
two fresh-process replays).
- **Verdict.** When the episode ends (the collect hook's SIGUSR1, after the agent's container is stopped), the service
  reads Meta-World's own success check on the live simulator's state after the last executed control step
  (`server_mw.py` `finalize()`: `S.check()`, i.e. `evaluate_state` as of the last `env.step`) and writes it to
  `final.json` as `success` = `live_success`, with `graded_by = "live"`, `replays = 0`, the live end state's hash
  (`state_sha` = `live_state_sha`) and `"finalized": true`, in one atomic write. The check is a predicate on that one
  state, with no hold or settle window, so the live rule is the privileged twin's. An episode that ended on a simulator error (`reason = "error"`) is no success: `Session.step` raised before
  the check was updated, so it would report the step before while the state is the failed step's. The crash-recovery replay (the journal replayed to
  resume the same episode after a sidecar crash) stays: it grades nothing.
- **Start state.** Checked when the episode begins (`_check_start()`), before the agent is served: the instance's
  SHA-256 must be `RCB_INSTANCE_SHA` and the restored scene's state hash (SHA-256 of the MuJoCo integration state)
  must be `RCB_START_SHA`, both set in `environment/docker-compose.yaml` from the frozen
  instance.
  A mismatch gives up with `reason = "instance_mismatch: ..."`, `infra_error = 1`.
- **Video.** One pass after the verdict is on disk (`render_video()`): a fresh session renders the recorded trajectory
  (`front` camera, at most about 600 frames, OSMesa on the CPU) to `replay.mp4` / `replay.last.png`;
  `video_source = "render"`, `video_pending` while it runs, then `video` and `video_done`. A failed, slow or crashed
  render loses only the video (a restarted service finds the verdict and idles). Recording during the episode was not
  chosen: the cameras are rendered only for what the agent asks for, and every extra OSMesa frame in its call path
  would slow its calls.
- **Collect hooks.** `rcb_monitor` seal, then `kill -9 -1` in the agent's container (nothing the agent left running
  drives the robot until the episode ends), then the sim hook: it waits for the PID file (at most
  180 s), sends SIGUSR1 every 30 s and waits for `video_done`, inside one 840 s deadline (`timeout_sec = 900`). The
  verdict itself takes well under a second; the deadline is for a crash resume (the journal replayed) and the video of
  the longest episode the 1800 s cutoff allows (the replay costs 0.2–0.9 ms per control step, plus about 0.1 s per
  frame).
- **Infrastructure** (`tests/grade.py`, `infra_error = 1`): `final.json` missing, unreadable, carrying `infra_error`
  (a give-up after crashes not all inside the agent's calls: `sim_crashed`, `resume_failed`; `instance_mismatch`) or
  `finalize_error`, or never finalized. The agent's 0: a live failure, a crash inside its calls
  (`sim_crashed_on_call`), a simulator error raised by its actions (`reason = "error"`), no actions. Video failures
  are never infrastructure. `reward.json`: `success`, `live_success`, `graded_by_live = 1`, `replays = 0`,
  `infra_error`, `sim_error`, `grader_error`, `finalized`, `missing_log`, `no_verdict`, `instance_mismatch` and the
  episode's counts; no `replay_success` / `deterministic`.
- **Compute.** The video pass is one scene build plus the episode's physics (0.2–0.9 ms per control step) plus its
  frames: seconds per trial, CPU.

`meta["time_s"]` / `meta["time_left_s"]` count from the agent's first request to the service (logged, so a crash
resume keeps it), not from the service's start: the service is up before the harness has installed the agent.

## Egress
Meta-World's scripted policies solve these tasks and are public (PyPI, GitHub), so `task.toml` closes agent egress to
the one allowlist (`network_mode = "allowlist"`, the hosts of `scripts/set_agent_egress.py`), as DexToolBench does. That
list has the package registries, so the PyPI distribution `metaworld`, which ships those policies, is reachable: the
instruction's honour rule asks the agent not to fetch a solution, nothing blocks it, and a trial
that installs `metaworld` is one to look at (PROTOCOL §5). The
policies are deleted from the image in the layer that installs them.

## Rebuilding
```bash
docker build -t ghcr.io/mll-lab-nu/efe:metaworld-$(cat images/metaworld/VERSION) \
    -f images/metaworld/Dockerfile images/metaworld          # ~780 MB
bash ci_checks/run_all.sh tasks/metaworldplus/metaworldplus-*
```

## Evidence
Measured when the instances were frozen, for all fifty environments: the instance is not
solved at the start; `reset()` is bit-exact; the oracle (Meta-World's scripted policy, up to its first success, 41–136
actions) succeeds; two replays in fresh processes end in the live state's hash and succeed (the reference's
determinism, which the trajectory deliverable and the privileged verifier rely on).

Harbor runs on the generated tasks: `-a oracle` scores 1 (50/50 privileged, 6/6 standard sampled), `-a nop` 0. Two scripted cheat attempts score 0: in privileged mode, tooling patched to report success, forged
reward files and a do-nothing trajectory; in standard mode, hidden endpoints (`/reset`, `/state`, `/success`: 404), a
wrong action type and `dt` (400), and a forged `final.json` in the agent's container (never collected).

## Screening

The benchmark owner's screening (ten runs, one trial per run and task directory). A directory is **easy** when a run solved it: a graded success within the task's time limit.
Where only one or two of the later runs solved a directory Luna had failed, their logs were checked for shortcuts and
for any access to tests, solutions or graders. It is **hard** when GPT-6 Luna and every later run that attempted it
failed, GPT-6 Astra and Claude Opus 5.5 among them; a standard directory that only Astra solved is hard as well. It is
**unverified** when only Luna attempted it and failed (the later runs only take bases Luna solved in no mode), and
**pending** without a Luna verdict. A base whose every mode is easy, and every base Luna solved in some mode, is left out of the core set (`docs/core_set.toml`); its tasks keep their names.

Runs: Luna `codex-gpt6_luna-xhigh`; Astra `codex-gpt6_astra-high`; Opus `claude_code-opus_5_5-high`; Sol 6.1
`codex-gpt6_1_sol-high`; Sol `codex-gpt6_sol-high`; Gemini 3.8 Flash `antigravity_cli-gemini_3_8_flash-high`; Gemini 4
Argon `antigravity_cli-gemini_4_argon-high`; DeepSeek V4.1 Flash `dsh-deepseek_v4_1_flash-high`; GLM 5.3 Flash
`claude_code-glm_5_3_flash-high`; Qwen3.8 27B `claude_code-qwen3_8_27b-high`.

By directory: 79 easy, 0 hard, 21 unverified, 0 pending.

| base | privileged | standard |
|---|---|---|
| `metaworldplus-assembly-i00` | easy: Luna | easy: Luna |
| `metaworldplus-basketball-i00` | easy: Luna | unverified |
| `metaworldplus-bin-picking-i00` | easy: Luna | easy: Luna |
| `metaworldplus-box-close-i00` | easy: Luna | easy: Luna |
| `metaworldplus-button-press-i00` | easy: Luna | easy: Luna |
| `metaworldplus-button-press-topdown-i00` | easy: Luna | unverified |
| `metaworldplus-button-press-topdown-wall-i00` | easy: Luna | unverified |
| `metaworldplus-button-press-wall-i00` | easy: Luna | easy: Luna |
| `metaworldplus-coffee-button-i00` | easy: Luna | easy: Luna |
| `metaworldplus-coffee-pull-i00` | easy: Luna | easy: Luna |
| `metaworldplus-coffee-push-i00` | easy: Luna | easy: Luna |
| `metaworldplus-dial-turn-i00` | easy: Luna | easy: Luna |
| `metaworldplus-disassemble-i00` | easy: Luna | unverified |
| `metaworldplus-door-close-i00` | easy: Luna | easy: Luna |
| `metaworldplus-door-lock-i00` | easy: Luna | unverified |
| `metaworldplus-door-open-i00` | easy: Luna | unverified |
| `metaworldplus-door-unlock-i00` | easy: Luna | unverified |
| `metaworldplus-drawer-close-i00` | easy: Luna | easy: Luna |
| `metaworldplus-drawer-open-i00` | easy: Luna | unverified |
| `metaworldplus-faucet-close-i00` | easy: Luna | unverified |
| `metaworldplus-faucet-open-i00` | easy: Luna | easy: Luna |
| `metaworldplus-hammer-i00` | easy: Luna | easy: Luna |
| `metaworldplus-hand-insert-i00` | easy: Luna | unverified |
| `metaworldplus-handle-press-i00` | easy: Luna | easy: Luna |
| `metaworldplus-handle-press-side-i00` | easy: Luna | easy: Luna |
| `metaworldplus-handle-pull-i00` | easy: Luna | unverified |
| `metaworldplus-handle-pull-side-i00` | easy: Luna | unverified |
| `metaworldplus-lever-pull-i00` | easy: Luna | unverified |
| `metaworldplus-peg-insert-side-i00` | easy: Luna | unverified |
| `metaworldplus-peg-unplug-side-i00` | easy: Luna | unverified |
| `metaworldplus-pick-out-of-hole-i00` | easy: Luna | easy: Luna |
| `metaworldplus-pick-place-i00` | easy: Luna | easy: Luna |
| `metaworldplus-pick-place-wall-i00` | easy: Luna | unverified |
| `metaworldplus-plate-slide-back-i00` | easy: Luna | easy: Luna |
| `metaworldplus-plate-slide-back-side-i00` | easy: Luna | easy: Luna |
| `metaworldplus-plate-slide-i00` | easy: Luna | easy: Luna |
| `metaworldplus-plate-slide-side-i00` | easy: Luna | easy: Luna |
| `metaworldplus-push-back-i00` | easy: Luna | easy: Luna |
| `metaworldplus-push-i00` | easy: Luna | unverified |
| `metaworldplus-push-wall-i00` | easy: Luna | unverified |
| `metaworldplus-reach-i00` | easy: Luna | easy: Luna |
| `metaworldplus-reach-wall-i00` | easy: Luna | easy: Luna |
| `metaworldplus-shelf-place-i00` | easy: Luna | easy: Luna |
| `metaworldplus-soccer-i00` | easy: Luna | easy: Luna |
| `metaworldplus-stick-pull-i00` | easy: Luna | unverified |
| `metaworldplus-stick-push-i00` | easy: Luna | unverified |
| `metaworldplus-sweep-i00` | easy: Luna | unverified |
| `metaworldplus-sweep-into-i00` | easy: Luna | easy: Luna |
| `metaworldplus-window-close-i00` | easy: Luna | easy: Luna |
| `metaworldplus-window-open-i00` | easy: Luna | easy: Luna |
