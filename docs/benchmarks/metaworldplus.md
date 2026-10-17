# MetaWorld+

All fifty of [Meta-World](https://github.com/Farama-Foundation/Metaworld)'s v3 environments (Sawyer arm, reward v2),
each on one frozen instance, in both modes: 100 tasks.

| | |
|---|---|
| upstream | Meta-World @ `59fc34d7768af9785e4688c3e1db671424f4a6c3` (MIT), MuJoCo 3.3.0, gymnasium 1.1.1 |
| tasks | `tasks/metaworldplus-<env>-i00-privileged` and `tasks/metaworldplus-<env>-i00-standard` (twins share the instance) |
| metadata | `simulator = "mujoco"`, `robot = "sawyer"`, `family = "metaworld/<env>"`, `oracle = "full"` |
| image | `ghcr.io/mll-lab-nu/eai-metaworld:0.1.0` (`images/metaworld/`), CPU only |
| standard client | the one client base and pins of `scripts/eai_standard/` (`client.env`, `client-requirements.txt`); `rcb_client.py` / `rcb1.py` byte copies of the MuJoCo standard tasks' (accepting both protocol spellings) |
| generator | `scripts/metaworldplus/` (`freeze.sh` → `frozen/`, `generate.py` → `tasks/`) |

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
  instructions state it in words (`scripts/metaworldplus/envs.py` `SUCCESS`, one sentence per environment, read from
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
  is rendered from (see the change log below). No object poses, no reward, no success signal. Meta-World's
  per-camera views `corner*` are left out: they render upside down.

## Standard-mode service (`images/metaworld/standard/server_mw.py`)
Derived from `images/mujoco/limited/server_mj.py` and identical in protocol and lifecycle (four endpoints, RCB1, no
reset, journal + per-call checkpoints with at most two resumes, startup watchdog, SIGUSR1 collect hook, `/data`
evidence, verdict before video). Differences:
1. The action type comes from the tool module (`mw_tool.ACTION_TYPE`: `ee_delta`) instead of a fixed `joint_position`.
2. Watching (`/observe` with `seconds > 0`) holds the hand still (`S.hold_targets()`), since actions are deltas.
3. Cameras and proprioception come from the tool module (`CAMERA_VIEWS`, `PROPRIO_LAYOUT`); `meta.task` is the target.
4. DexToolBench's goal logic is gone.
5. As in the MuJoCo service after the migration (PROTOCOL §7): a simulator error (500) ends the episode with
   `reason = "error"`, a body over 64 MB gets 413; a request is validated in full before any physics, and a malformed
   one (`dt` / `seconds` / `video_fps` not a finite number, `cameras` not a list of names, actions that are not a
   numeric array) is a 400 that changes nothing; `final.json` carries
   `replay_success` / `live_success` and the grader writes numeric fields only; `/status` and `meta` also carry
   `sim_steps`, submit responses `clipped`.

Protocol: `eai-standard/2.1` (`/spec`, `task.toml`, instructions). `generate.py` finishes every task with
`scripts/task_conventions.py` `normalize` (README layout, no `results/`), and `--check` is clean on all 100.

Agent results are not in the repository (PROTOCOL D3): they are published on the results site.

## Verdict, video and the collect hook
`final.json` is written atomically and is `finalized` as soon as the verification replay's verdict is in it. The replay
video is rendered after that (to a temporary file, renamed when complete) and sets `video` and `video_done`; it cannot
change, hide or delay the verdict. The collect hook waits for the PID file (at most 180 s), then for `video_done`,
inside one 840 s deadline, so it always ends before its `timeout_sec = 900`; if it stops while the video is still
rendering, the verdict on disk is graded. `tests/grade.py` writes `infra_error = 1` (no verdict on the agent) when
`final.json` is missing, unreadable, carries `infra_error` / `finalize_error`, or was never finalized (the service did
not reach a verdict before the hook gave up), and a plain 0 only for a verdict that says so. Episodes have no step limit
(D1); the verification replay costs 0.2–0.9 ms per recorded control step (the stick and coffee environments are the
slowest), so an episode of roughly a million control steps or more (over three hours of robot time, reachable only by
stepping without video for many minutes) may not get its verdict inside the hook; it is then reported as `infra_error`,
not as a failure. A technical step cap that would turn that
case into a verdict (as DexToolBench's 360,000 steps do) is an open decision.

`meta["time_s"]` / `meta["time_left_s"]` count from the agent's first request to the service (logged, so a crash
resume keeps it), not from the service's start: the service is up before the harness has installed the agent.

## Change log
- 2026-10-10 (review 0067, findings M3, M4, M6, M7, M9). **Observation change, standard mode, all 50 tasks:** the
  calibration's `cam2world_gl` held the position of MuJoCo's left-eye camera (`scene.camera[0]`), 3.4 cm to the side of
  the viewpoint the mono image is rendered from (`vis.global.ipd` = 0.068); it now gives that viewpoint (a free
  camera: the mean of the two eye cameras; `topview`: `data.cam_xpos` / `cam_xmat`). Points back-projected from depth
  were off by 3.4 cm, against tolerances that start at 2 cm, so **standard-mode results from before this date are not strictly
  comparable** with later ones. **Text change, both modes:** the instructions state each environment's success
  condition (above); the earlier standard text ("the task's object against `target_pos`, with a tolerance of a few
  centimetres") left out stick-push's and stick-pull's final-state conditions and did not describe hammer, lever-pull,
  door-open and disassemble. Earlier stick-push / stick-pull standard results were obtained under the incomplete text.
  **No change to what counts as success:** the check, instances and oracles are the same. Also: request validation
  before physics (`dt = Infinity` and the like were a 500 that ended the episode), `finalized` set with the verdict
  instead of after the video, `infra_error` for a missing / unreadable / verdict-less `final.json`, the collect hook's
  loop inside its timeout (it could run 980 s against 900), the agent's clock, the limits on a hand-written
  `trajectory.npz` stated in the privileged instruction. Each task README has the entries that apply to it.

## Egress
Meta-World's scripted policies solve these tasks and are public (PyPI, GitHub), so `task.toml` closes agent egress to
the one allowlist (`network_mode = "allowlist"`, the hosts of `scripts/set_agent_egress.py`), as DexToolBench does. Since
2026-10-11 that list has the package registries, so the PyPI distribution `metaworld`, which ships those policies, is
reachable again: the instruction's honour rule asks the agent not to fetch a solution, nothing blocks it, and a trial
that installs `metaworld` is one to look at (PROTOCOL §2.11). The
policies are deleted from the image in the layer that installs them; `freeze.sh` mounts them from the pinned commit.

## Rebuilding
```bash
docker build -t ghcr.io/mll-lab-nu/eai-metaworld:$(cat images/metaworld/VERSION) \
    -f images/metaworld/Dockerfile images/metaworld          # ~780 MB
bash scripts/metaworldplus/freeze.sh            # instances + oracles -> scripts/metaworldplus/frozen/ (~1 min)
python3 scripts/metaworldplus/generate.py       # -> tasks/metaworldplus-* ; re-running reproduces them exactly
cd tasks && harbor add --scan . && cd ..
bash ci_checks/run_all.sh tasks/metaworldplus-*
```
`scripts/build_images.sh` still names images `rcb-<name>`; until the migration, build this one with the command above.
`freeze.sh` re-creates every instance and oracle, so the task digests change only if the image or Meta-World changes.

## Evidence
`scripts/metaworldplus/frozen/report.json` (written by `freeze.sh`), for all fifty environments: the instance is not
solved at the start; `reset()` is bit-exact; the oracle (Meta-World's scripted policy, up to its first success, 41–136
actions) succeeds; two replays in fresh processes end in the live state's hash and succeed. Instances reproduce
the earlier MetaWorld+ snapshots bit for bit (same seeds, same integration state).

Harbor runs on the generated tasks (AMD Ryzen 9 7950X, Docker, no GPU): `-a oracle` 50/50 privileged and 6/6 standard
(assembly, handle-press, handle-pull-side, soccer, stick-pull, sweep) score 1, deterministic; `-a nop` scores 0 on four
tasks per mode. Two scripted cheat attempts score 0: in privileged mode, tooling patched to report success, forged
reward files and a do-nothing trajectory; in standard mode, hidden endpoints (`/reset`, `/state`, `/success`: 404), a
wrong action type and `dt` (400), and a forged `final.json` in the agent's container (never collected).

## Easy set

The benchmark owner's screening of 2026-10-17 (results dashboard snapshot 2026-10-17T05:59:33Z; ten runs, one trial per
run and task directory). A directory is **easy** when a run solved it: a graded success within the task's time limit.
Where only one or two of the later runs solved a directory Luna had failed, their logs were checked for shortcuts and
for any access to tests, solutions or graders. It is **hard** when GPT-6 Luna and every later run that attempted it
failed, GPT-6 Astra and Claude Opus 5.5 among them; a standard directory that only Astra solved is hard as well. It is
**unverified** when only Luna attempted it and failed (the later runs only take bases Luna solved in no mode), and
**pending** without a Luna verdict. A base whose every mode is easy is in the easy set (`docs/easy_set.toml`, reason
`solved`): kept under its name and reported apart from the main table.

Runs: Luna `codex-gpt6_luna-xhigh`; Astra `codex-gpt6_astra-high`; Opus `claude_code-opus_5_5-high`; Sol 6.1
`codex-gpt6_1_sol-high`; Sol `codex-gpt6_sol-high`; Gemini 3.8 Flash `antigravity_cli-gemini_3_8_flash-high`; Gemini 4
Argon `antigravity_cli-gemini_4_argon-high`; DeepSeek V4.1 Flash `dsh-deepseek_v4_1_flash-high`; GLM 5.3 Flash
`claude_code-glm_5_3_flash-high`; Qwen3.8 27B `claude_code-qwen3_8_27b-high`.

29 of 50 bases are in the easy set; by directory: 79 easy, 0 hard, 21 unverified, 0 pending.

| base | easy set | privileged | standard |
|---|---|---|---|
| `metaworldplus-assembly-i00` | yes | easy: Luna | easy: Luna |
| `metaworldplus-basketball-i00` |  | easy: Luna | unverified |
| `metaworldplus-bin-picking-i00` | yes | easy: Luna | easy: Luna |
| `metaworldplus-box-close-i00` | yes | easy: Luna | easy: Luna |
| `metaworldplus-button-press-i00` | yes | easy: Luna | easy: Luna |
| `metaworldplus-button-press-topdown-i00` |  | easy: Luna | unverified |
| `metaworldplus-button-press-topdown-wall-i00` |  | easy: Luna | unverified |
| `metaworldplus-button-press-wall-i00` | yes | easy: Luna | easy: Luna |
| `metaworldplus-coffee-button-i00` | yes | easy: Luna | easy: Luna |
| `metaworldplus-coffee-pull-i00` | yes | easy: Luna | easy: Luna |
| `metaworldplus-coffee-push-i00` | yes | easy: Luna | easy: Luna |
| `metaworldplus-dial-turn-i00` | yes | easy: Luna | easy: Luna |
| `metaworldplus-disassemble-i00` |  | easy: Luna | unverified |
| `metaworldplus-door-close-i00` | yes | easy: Luna | easy: Luna |
| `metaworldplus-door-lock-i00` |  | easy: Luna | unverified |
| `metaworldplus-door-open-i00` |  | easy: Luna | unverified |
| `metaworldplus-door-unlock-i00` |  | easy: Luna | unverified |
| `metaworldplus-drawer-close-i00` | yes | easy: Luna | easy: Luna |
| `metaworldplus-drawer-open-i00` |  | easy: Luna | unverified |
| `metaworldplus-faucet-close-i00` |  | easy: Luna | unverified |
| `metaworldplus-faucet-open-i00` | yes | easy: Luna | easy: Luna |
| `metaworldplus-hammer-i00` | yes | easy: Luna | easy: Luna |
| `metaworldplus-hand-insert-i00` |  | easy: Luna | unverified |
| `metaworldplus-handle-press-i00` | yes | easy: Luna | easy: Luna |
| `metaworldplus-handle-press-side-i00` | yes | easy: Luna | easy: Luna |
| `metaworldplus-handle-pull-i00` |  | easy: Luna | unverified |
| `metaworldplus-handle-pull-side-i00` |  | easy: Luna | unverified |
| `metaworldplus-lever-pull-i00` |  | easy: Luna | unverified |
| `metaworldplus-peg-insert-side-i00` |  | easy: Luna | unverified |
| `metaworldplus-peg-unplug-side-i00` |  | easy: Luna | unverified |
| `metaworldplus-pick-out-of-hole-i00` | yes | easy: Luna | easy: Luna |
| `metaworldplus-pick-place-i00` | yes | easy: Luna | easy: Luna |
| `metaworldplus-pick-place-wall-i00` |  | easy: Luna | unverified |
| `metaworldplus-plate-slide-back-i00` | yes | easy: Luna | easy: Luna |
| `metaworldplus-plate-slide-back-side-i00` | yes | easy: Luna | easy: Luna |
| `metaworldplus-plate-slide-i00` | yes | easy: Luna | easy: Luna |
| `metaworldplus-plate-slide-side-i00` | yes | easy: Luna | easy: Luna |
| `metaworldplus-push-back-i00` | yes | easy: Luna | easy: Luna |
| `metaworldplus-push-i00` |  | easy: Luna | unverified |
| `metaworldplus-push-wall-i00` |  | easy: Luna | unverified |
| `metaworldplus-reach-i00` | yes | easy: Luna | easy: Luna |
| `metaworldplus-reach-wall-i00` | yes | easy: Luna | easy: Luna |
| `metaworldplus-shelf-place-i00` | yes | easy: Luna | easy: Luna |
| `metaworldplus-soccer-i00` | yes | easy: Luna | easy: Luna |
| `metaworldplus-stick-pull-i00` |  | easy: Luna | unverified |
| `metaworldplus-stick-push-i00` |  | easy: Luna | unverified |
| `metaworldplus-sweep-i00` |  | easy: Luna | unverified |
| `metaworldplus-sweep-into-i00` | yes | easy: Luna | easy: Luna |
| `metaworldplus-window-close-i00` | yes | easy: Luna | easy: Luna |
| `metaworldplus-window-open-i00` | yes | easy: Luna | easy: Luna |
