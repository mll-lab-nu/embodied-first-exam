# RoboLab

[NVIDIA RoboLab](https://github.com/NVlabs/RoboLab) v0.3.1 on Isaac Lab 2.3.2 / Isaac Sim 5.1: tabletop language-goal tasks
for a Franka with a Robotiq 2F-85 (DROID joint-position actions). `simulator = "robolab"`, `robot = "franka-robotiq-2f85"`.
53 families, each as a privileged task `robolab-<family>-i00-privileged` and its standard twin
`robolab-<family>-i00-standard` (`eai-standard/2.2`), on the same frozen instance. On 2026-10-14 the success rule changed
in place (Success semantics; PROTOCOL v2.0 §1, H.8: a new DIGEST, results are attributed by digest): results recorded
under the earlier DIGESTs are not comparable with the current ones; `scripts/robolab/regrade.py` re-grades them
(Re-grading).

## Tasks and generator
- One generator: `python3 scripts/robolab/mk_tasks.py` writes every RoboLab task dir (both modes) from
  `scripts/robolab/` alone: `families.json` (per family: RoboLab's task class and file, the goal, the success term's
  source, the texts of both modes, the oracle level, the cited positives), `instances/<family>.json` (the frozen
  instances), `oracles/<family>/` (the reference solutions and the standard oracle's recorded joint targets), `shared/`
  (the tooling `rcb_robolab.py`, the oracles' skills `ref_primitives.py`), `template/<mode>/` (every other task file) and
  `scripts/eai_standard/` (the 2.2 layer and the standard client). Both twins of a family are written to a scratch
  directory, passed through `scripts/task_conventions.py`'s `normalize()` (the v1.0 conventions: names, README layout,
  `rm -rf /logs/verifier/*` first in `test.sh`, no `results/`) and then synced into `tasks/`. Re-running it leaves
  `git diff tasks/` empty; `--check` only compares.
- A family is RoboLab's benchmark task of that name, its success predicate RoboLab's own `success` termination term.
  `families.json` holds the 53 families that have tasks: the 2 with a reference solution and the 51 with
  a graded positive example. 35 further RoboLab tasks were frozen but have no positive yet (PROTOCOL §2.7 needs one
  before review); their entries and instances are not kept here (repository history, 9621e47d1).
- The frozen instance is the full scene state after RoboLab's canonical seeded reset (`env.reset()` twice, as RoboLab's
  evaluation loop does), with its state hash, made in the image by `rcb_robolab.py make-instance --task <f> --seed 0`;
  the tasks carry it in `environment/` and `tests/` (privileged) and `environment/sim/` (standard). Each instance was
  checked in a second fresh process: the same hash, success false at t = 0 and during a 1 s hold.
- New family: add its entry to `families.json` and `instances/`, then run the generator and `cd tasks && harbor add --scan .`.

## Oracle and review (PROTOCOL §2.7)
- banana_in_bowl and rubiks_cube_left_of_bowl have a reference solution: `solution/oracle_<family>.py`, a human-written
  script on the privileged tooling plus the skills in `solution/ref_primitives.py` (never in the agent image); the
  standard oracle streams the privileged oracle's recorded joint targets through the client in one-second chunks and
  rides through a service crash (`spec.on_service_error`). The labels follow the recorded runs (static validation):
  - privileged `oracle = "full"`: the oracle scored 1 in recorded Harbor runs on a byte-identical grader, frozen instance
    and oracle code, and every tooling change since is off the oracle / replay path (eaf2aff0: other families' registry
    entries; b3c7ca89: additive 2.2 helpers, re-checked with the same final state sha through the same path; cde31660:
    the depth default, which run-oracle and replay pass explicitly); `oracle_evidence` cites the runs;
  - standard `oracle = "partial"`: oracle_replay scored 1 in 6/6 recorded runs on the pre-crash-recovery service with the
    same verdict formula, and has not been re-run on this version.
- `oracle = "none"` (51 families): RoboLab ships no expert or planner. Every such family has at least one model trial that
  the separate verifier scored 1 (run `codex-gpt6_luna-xhigh`), cited by trial id in `oracle_evidence` and in the README
  with its trial log on the results site and its replay video on Hugging Face (results are not kept in task directories,
  PROTOCOL D3; three standard positives of the withdrawn rcb-limited/2.0 batch are unpublished). These tasks have no
  `solution/` and go through human review per family in PR #3 (both modes, a positive, the `nop` result).
- bananas_in_bin_one_more and bananas_in_bin_three_total have the identical predicate (exactly 1 of `banana`,
  `banana_01`, `banana_03` in `grey_bin`, RoboLab's `choose`, K = 1); only their instructions differ.

## Success semantics (instantaneous)
RoboLab evaluates its `success` term after every control step and terminates the episode at the first step where it
holds (its termination freezes the env); the replay stops there and later rows are never executed. So a goal state that
holds at a single control step counts, in both modes. This is "success at any step" rather than "at the end of the
replay" (PROTOCOL §3): we keep RoboLab's own definition so the predicate is upstream's. Most predicates require
the gripper to have released the object (`require_gripper_detached`), which rules out holding an object through the goal
region; the instructions state the rule in both modes. Three changes on 2026-10-14 ( the failure analysis of the
10-14 results found 19 of 194 successes that fired before the task was done), all in the tooling (`rcb_robolab.py`):
- **"The gripper" is both fingers.** RoboLab's DROID robot declares one contact body, `left_inner_finger`
  (`robolab/robots/droid.py`, "Use one finger only": an Isaac Lab contact sensor with filters takes one prim), so an
  object pinched by the right finger or the pads read as released and 9 successes fired with the object still clamped.
  `GRIPPER_CONTACT` declares both inner fingers and makes "gripper" RoboLab's own alias group of the two
  (`WorldState.resolve_contact_bodies`: any member), set before the env is registered; each finger gets RoboLab's own
  sensors. Every family's term is otherwise upstream's.
- **On the table where the words say so.** `take_measuring_spoon_out` ("... and put it on the table") and
  `cooking_clear_plate` (RoboLab's specific wording: "place each on the table surface") use RoboLab's own
  `object_outside_of_and_on_surface` with surface `table` and their own parameters instead of `object_outside_of`,
  which counted an object lifted out of the container or knocked off the table (5 successes).
- **A settle hold at the end.** After a trajectory's last row the replay holds it for `SETTLE_STEPS` (30 control steps,
  2 s), the term still checked at every step, so a release in the last rows completes (a trajectory recorded before
  that ended at the old success step ends the same way); in standard mode the service holds the last command as long
  when the agent's phase ends, and the fresh-process replays run the recorded episode as it is (`replay --no-settle`).

## Image and host
- `images/robolab/` (Isaac Lab 2.3.2 / Isaac Sim 5.1 from the pinned `uv.lock`, RoboLab's Apache-2.0 asset library baked
  in), tagged `ghcr.io/mll-lab-nu/eai-robolab:<images/robolab/VERSION>` (0.1.2 = 0.1.1, the same build as
  the former `rcb-robolab:0.1.1`, plus one layer with the remote files of the asset library: Network, below). It
  contains NVIDIA Isaac Sim, whose licence forbids redistribution: **BUILD_ONLY**.
  `images/robolab/BUILD_ONLY` has the licences, the build command
  (`docker build -f images/robolab/Dockerfile -t ghcr.io/mll-lab-nu/eai-robolab:$(cat images/robolab/VERSION) .`),
  the check of a build and how a CI machine builds it. A host that has the old tag only needs `docker tag`.
- Isaac needs an RTX-class GPU even headless (PhysX runs on the CPU). One Isaac simulator at a time per 32 GB of host RAM.
- Standard mode: the agent container and the verifier use the one digest-pinned client image of every standard task and
  its exact pip pins (`scripts/eai_standard/client.env`, `client-requirements.txt`, copied into `environment/`); only the
  `sim` sidecar uses eai-robolab.
- Isaac keeps generated Python in its Kit cache: the verifier and the standard sidecar mount their own `*_trusted` cache
  volumes, never the agent's; every cache volume is scoped to the trial's compose project (no fixed name).

## Network
The agent reaches the model APIs and, since 2026-10-11, the package registries (PyPI, apt archives), nothing else: `[agent] network_mode = "allowlist"` with the hosts of
`scripts/set_agent_egress.py`, in both templates' `task.toml.tmpl` (`mk_tasks.py` fills the host list from that script;
owner decision 2026-10-10, board 0072). Until then the tasks had Harbor's default, public egress, the repository-wide
default of 2026-09-24 (kept on 2026-10-02) with which the templates were written; no reason specific to RoboLab was
recorded. One existed, found when the allowlist was first run on a real simulator (2026-10-11), and image 0.1.2 removes
it: the second point.

| Service | Before | Since 2026-10-10 |
|---|---|---|
| privileged `main` (agent and its Isaac processes) | public | public from container start until the agent starts (the harness is installed then), the allowlist (the model APIs and the package registries) while the agent runs |
| standard `main` (agent, client only) | public | the same |
| standard `sim` (the simulator service) | public | the same as `main`: Harbor's egress control puts every compose service without a network setting of its own in one namespace, so the service's Isaac start (it begins at container start and takes 5 to 9 minutes) and a restart after a crash run with the allowlist only; public again while the collect hook replays the episode |
| `rcb_monitor` | none | none |
| privileged verifier | public (Harbor's default) | unchanged |
| standard verifier | none (`no-network`) | unchanged |

- **Isaac itself needs no network**: the image holds Isaac Sim, Isaac Lab, RoboLab and every Python package, and the EULA
  is accepted by environment variables. With only the model APIs reachable the oracle of `banana-in-bowl` scores 1 in
  both modes with the same initial and final state hashes as with open egress (`deterministic` 1, `instance_ok` 1, live =
  replay; L40S hosts, 2026-10-11), and a probe from inside the agent's container finds GitHub, PyPI, Hugging Face and
  NVIDIA's Omniverse content bucket unreachable while the OpenAI, Anthropic and OpenRouter APIs answer.
- **RoboLab's asset library did, until image 0.1.2.** 15 of its USD layers reference NVIDIA's public Omniverse content
  bucket (`omniverse-content-production.s3…amazonaws.com`) by URL: the MDL materials of the four tables, of the grey bin
  and of the robot, their textures, and a few props of scenes that are not tasks here; the scenes of 43 of the 53
  families load some of them. Kit fetched them whenever a scene was built. On 0.1.1 under the allowlist the fetches
  fail (`could not find module … in module path`, `Unable to find SdrShaderNode`): the table renders as a glossy red
  surface instead of wood (64 % of the pixels of the front camera's first frame differ from the open-egress frame, 77 %
  of the wrist camera's, 16 % of the shoulder camera's) and the scene is ready later (501 to 640 s against 333 to
  428 s), while physics is unchanged (none of the 53 families references remote geometry). Image 0.1.2 holds the files:
  `images/robolab/mirror_remote_assets.py`, the last step of the build, copies all 419 (635 MB) to
  `/opt/robolab/assets/_remote`, checks each against `images/robolab/remote_assets.sha256` and points the layers at the
  copies; no layer of the library names a remote file any more. Checked from the published 0.1.2 under the
  allowlist (2026-10-11, L40S hosts, the oracle of `banana-in-bowl`): reward 1 in both modes with the state hashes of
  the open-egress runs, no material error in Kit's log, the scene ready after 321 to 341 s, and first frames that
  differ from the open-egress ones in 0.02 to 0.7 % of the pixels (render noise), in the standard service's cameras and
  in the privileged tooling's.
- **The privileged verifier** keeps Harbor's default network (Grading and determinism); since 0.1.2 it does not need it
  for the materials either.
- **The recorded example episode is not in the agent's image.** RoboLab's repository ships one recorded successful
  episode (`examples/recorded_data/RubiksCubeAndBananaTask`: actions, video and environment configuration, replayed by
  `examples/run_recorded.py`), a solution of `rubiks_cube_and_banana` inside the base image. The privileged
  `environment/Dockerfile` removes the directory (since 2026-10-10); nothing at run time reads it. The standard agent
  container has no simulator image, and the verifier's image is not the agent's.

## Time budget (D8)
**Since 2026-10-12: 3600 s** for every task of both modes (owner: stricter cutoffs in 30-minute steps, one number for both modes; history in [`../CUTOFFS.md`](../CUTOFFS.md)). The text below describes the budget before that, 5400 s, and why it was chosen; results are grouped by budget.

The number is each task's own `[agent] timeout_sec`, written by the generator (PROTOCOL §2.12; history in [`../CUTOFFS.md`](../CUTOFFS.md)), and
every instruction states it in its closing `## Time limit` section; the benchmark's own text names no number. On
2026-10-11: 5400 s for every task of both modes, longer than the default 3600 s: every Python process pays about 2 minutes of Isaac
launch and scene build, so an agent's iterations cost more than in the other simulators; with 3600 s most failures in
our first sweep were agents running out of time mid-attempt (raised 2026-09-26, uniform since).

## Grading and determinism
- PhysX on the CPU: on one host a fresh process reproduces the live run bit for bit, but a second replay inside one
  process drifts in the last bits, so the verifier replays in **two fresh processes** and compares them. Across hosts the
  final state can differ in the last bits (the banana_in_bowl oracle ends in one of two hashes on our hosts, both
  successes): a trial is graded on the host it ran on.
- Privileged: `tests/grade.py` replays `/app/output/trajectory.npz` twice; success = the predicate held in both, the final
  hashes agree, and the rebuilt frozen scene matches the recorded one.
- Standard (since 2026-10-17, owner, boards 0150/0151): graded by the **live episode**, with no grading replay. The
  service judges the episode it runs: RoboLab's success term after every control step (the first step where it holds
  ends the episode), and when the agent's time is up (the collect hook's signal, after the agent's container is stopped)
  it holds the last command for `SETTLE_STEPS` = 30 more control steps on the live simulator while the term is checked
  (`settle_steps`; since 2026-10-14, the same hold the privileged replay applies after a trajectory's last row; a
  simulator error during the hold is recorded, `settle_error`, and the term is judged as it stands). It then
  writes `trajectory.npz` (the deliverable) and `episode.json` and exits; the hook (`environment/sim/finalize.sh`) writes
  `final.json` from it (`graded_by` "live", `replays` 0) before anything else. success = the live success, no
  infrastructure failure. The standard verifier only reads `final.json` and runs with `network_mode = "no-network"`.
  Until 2026-10-17 the hook replayed the trajectory in two fresh processes (`--no-settle`) and success was
  live ∧ replay ∧ deterministic; re-scoring such a trial by its live episode: `final.json` `success` (the live result, merged
  from episode.json; it already included the 2026-10-14 term and hold for trials on that version), `infra_error` only
  when the live record is missing (no or unfinalized `final.json`, no `live_sha`: no episode.json, or the service never
  ended the episode) or the service gave up with `infra_error` (`sim_crashed`, `resume_failed`); `replay_error`,
  `gpu_lost` and `instance_mismatch` found by a replay are not the live episode's; trials re-graded by board 0130
  (`regrade_*` in reward.json) keep their recorded verdict.
- The start state (standard): the service builds the frozen scene and, before it serves anything, compares it with the
  instance's recorded state: the state hash (`instance.json` `state_sha`) or, if the hash differs, every object pose and
  robot joint within the tooling's tolerance (`Session.instance_matches`, as the tooling's strict mode). A scene that
  matches neither is a give-up as an infrastructure failure (`instance_mismatch`, `infra_error` = 1; the service answers
  409). Before 2026-10-17 the strict check raised, the service crashed and restarted until the hook timed out.
- The privileged verifier keeps Harbor's default network (PROTOCOL §2.6 recommends no-network): it starts Isaac Sim, and
  a Kit start in a container without any network interface has not been tested on our hosts (with only the model APIs
  reachable it starts and builds the scene: Network). Grading downloads nothing: RoboLab's assets, since image 0.1.2 the
  remote files they reference too, and every package are in the image.
- Whose failure a 0 is (2026-10-10). Standard: `tests/grade.py` writes a reward whatever it finds; a missing, unreadable
  or unfinalized `final.json` (the service never came up, the collect hook was killed), a lost GPU, or a replay process
  that ended without a result (`replay_error`: Isaac died, its time limit) is `infra_error = 1`, never the agent's 0.
  `finalize.sh` replaces `final.json` atomically, retries a replay that died once, and counts a replay as done when its
  result line was printed (Isaac crashing at shutdown afterwards does not matter). Privileged: a deliverable that is not a
  readable trajectory (not an npz, no `task` / `actions`, object arrays, wrong shape, NaN, more than 100,000 rows) is
  `bad_trajectory` (the agent's 0); a replay process without a result, a replay time-out (`replay_timed_out`) and
  `instance_ok = 0` (the rebuilt scene differs on this host) set `grader_error = infra_error = 1`.
- Time limits (2026-10-10; rates from this file: Isaac start + scene ~2 min, replays 15-20 control steps/s). Privileged:
  each replay has max(1800 s, 900 s + rows / 7.5) (half the nominal rate), and `[verifier] timeout_sec = 29100` fits two
  replays of the longest accepted trajectory (100,000 rows: 14,234 s each) plus 600 s; before, the 2400 s verifier limit
  was shorter than two 1800 s replays. Standard: `[[verifier.collect]] timeout_sec = 15000` = the episode end (up to
  2700 s through a resume) + two replays of up to 5700 s (an Isaac start + an episode stepped for the whole 5400 s budget)
  + 900 s, until 2026-10-17; now `timeout_sec = 3600` (`HOOK_BUDGET_S`, the same number) = the episode end (up to 2700 s
  through a resume) + the video encode (at most 600 s, CPU, at most 3001 frames) + a margin, and the hook uses no GPU after
  the service exits. The saving: the two fresh-process replays, 333-377 s each at the median and 1600-2400 s at the p90
  over the 168 archived standard trials (an Isaac start of ~40-90 s + the episode at the live rate), on the trial's GPU.
- Tests without a simulator (numpy only): `scripts/robolab/tests/test_*.py`, each run as a script (RoboLab and YAMLab
  together): both graders on synthetic records, the whole `finalize.sh` with stand-ins for the service's end and the video
  encode (live success / failure / settle failure, crashes between and inside calls, instance mismatch, no episode.json,
  a failing, crashing or hanging encode; no case may start a replay), the tooling's replay CLI with a failing video, and the
  real `server.py` on the real shared layer with a stub simulator over HTTP (malformed requests, the step cap, the start
  check, the live video's frames and a broken camera).
- The video (standard, since 2026-10-17) is filmed during the live episode by the service (`live_video.py`): Isaac Lab
  renders every camera with each control step anyway (the observation), so a frame (the tooling's `_video_frame`: the
  viewport cameras + the wrist camera) is taken every 3 control steps (5 per simulated second) and written as a JPEG file
  (`/data/live_video/`, crash-safe; a resume skips the frames on disk and deletes those of the call lost in the crash); past 3000 slots the slot doubles (a time lapse).
  Cost: one JPEG encode per 3 control steps (a few ms against 70-300 ms per control step; the archived filmed replays,
  which filmed every step, took 1.1x the unfilmed ones). The collect hook encodes `live.mp4` + `live.last.png` after the
  verdict (CPU, `RCB_VIDEO_LIMIT_S` 600 s); a frame or an encode that fails costs the video only (`video` false,
  `video_error`), never the verdict. Privileged: the replay video never decides a replay: the tooling catches a writer
  that cannot open, a frame that cannot be rendered or written and an encoder that fails at close (`video_ok` false in the
  replay's result; `stop_video()` returns None), and the frames go straight to the encoder. A trajectory longer than
  9,000 control steps is filmed as a time lapse (at most 9,000 frames, `MAX_VIDEO_FRAMES`).
- `scripts/robolab/regrade.sh <task> <trial> <out>` re-grades a finished trial with the current task version in two fresh
  processes (the review's determinism check), on the host the trial ran on.

## Crash recovery (standard mode, docs/STANDARD_MODE.md §13)
- Resume class `exact`: the resumed service is a fresh process, and replaying the journal is that process's first replay,
  so the state hash at the last checkpoint must match exactly (else the episode ends `resume_failed`, `infra_error`).
- The journal holds the float32 row handed to `Session.step` for every control step; a checkpoint (state hash = sha1 of
  the scene's full state, proprio row) follows every call. Reading the state never steps physics. A resume replays the
  episode so far at about 15-20 control steps/s, on the agent's wall clock.
- `RCB_STARTUP_TIMEOUT_S = 900`: the scene builds measured 99-217 s (the Session build in the service logs of 25 standard
  trials on the laptop and ws3); 900 s is more than four times the slowest, so a host twice as slow keeps a 2x margin.
- Validation in this PR is static (user decision, 2026-10-01). The crash recovery was exercised on the CPU with a test
  double of the tooling under `run.sh` and a restart loop (kills inside and between calls, an exact-hash mismatch, three
  crashes inside calls, the 400s), with the shared layer's own selftest; `scripts/robolab/kill_test.sh` is the acceptance
  test on a GPU host (Harbor oracle, the service killed mid-episode). Per-call state hashing only reads the scene
  (`InteractiveScene.get_state` reads PhysX views into Isaac Lab's timestamped buffers and writes nothing), so it cannot
  change a live run; live == replay with per-call hashing on Isaac is still to be confirmed by a run.

## Tooling (file names)
| main's convention | RoboLab |
|---|---|
| `environment/rcb_traj.py` (privileged tooling, `Session`) | `environment/rcb_robolab.py` (`Session`: the frozen scene state, thin primitives, rendering, recording, replay) |
| `tests/rcb_traj.py` | `tests/rcb_robolab.py` |
| standard sidecar | `environment/sim/server.py` (the 2.2 adapter), `finalize.sh`, `rcb_robolab.py`; `run.sh`, `rcb_limited.py`, `rcb1.py` from `scripts/eai_standard/` |
| `rcb_client.py`, `rcb1.py` | the same names (`scripts/eai_standard/`) |

The tooling records (T, 8) actions (7 joint targets + the binary gripper command) at 15 Hz. Every copy of the tooling and
of the standard sidecar files is byte-identical across the benchmark (`check-tooling-identity.sh`); the tooling's TASKS
registry lists all 88 RoboLab tasks that were frozen (the 53 here and the 35 without a positive), so adding a family later does not change existing tasks.

## Declarations
- **Tooling: thin wrappers only.** Differential-IK moves, joint moves, gripper, hold, plus the frozen instance, state,
  recording, replay and rendering. Task-level skills (grasp, place, navigate) are never added to the agent's tooling;
  reference solutions keep theirs under `solution/`.
- **World-frame information (D7).** Standard tasks never say where things are in the world (STANDARD_MODE.md §10,
  `scripts/robolab/ci/advisory-world-frame.sh`); the robot's root frame (Franka base at the origin) is the world convention. Privileged tasks
  give the privileged state through the tooling.

## Standard mode (eai-standard/2.2)
`joint_position` (8: 7 joints + binary gripper, switched at the row; rows `dt` apart, a multiple of 1/15 s, anything else
is a 400) and `ee_pose` (8, closed-loop differential IK, at most 0.25 m/s, fingertip-centre frame); cameras
`egocentric_mirrored_camera`, `over_shoulder_left_camera` (static) and `wrist_cam` (on the Robotiq base link); Isaac
`distance_to_image_plane` depth; `/kinematics` from a numpy model of the USD joints (7); 32 proprio columns.
STANDARD_MODE.md §16.

Requests are checked completely before the first control step (PROTOCOL §4.6): a field of the wrong type (`dt`, `seconds`,
`video_fps`, `note`, `cameras`, `interpolate`, `video`, `type`, `depth`), a value out of range, an `ee_pose` position more
than 2 m from the robot's base on any axis or a zero quaternion is a 400 that executes nothing; an absent or null field
takes its default. Before 2026-10-10 some of these raised a TypeError / OverflowError, which the layer answers 500 and
which ends the episode (`reason = "error"`), and a non-string `note` failed after the chunk had run. One case is left in
the shared layer (`scripts/eai_standard/rcb_limited.py`): `actions` sent as a JSON object is converted before the adapter
sees it and still ends the episode with a 500.

## Known issues
- The tooling stops a runaway trajectory at 100,000 control steps (`step_guard`, 1.9 h of simulated time); the live
  service runs 3-15 steps/s, so the 5400 s budget ends an episode long before. Stated since 2026-10-10 in `/spec`
  (`max_control_steps`, `episode`) and in both instructions (PROTOCOL §4.5: a technical cap, not a step budget); a
  privileged trajectory may hold at most that many rows.
- An `ee_pose` submit has no frame cap: a long one at a high `video_fps` keeps many frames in memory (the client's
  defaults, 5 fps and mp4, stay small).
- RoboLab's success terms are upstream's (owner, 2026-10-14: "the original simulator decides"), except what 2026-10-14
  changes (Success semantics: both fingers, two on-table terms, the settle hold). Still looser than their words (board
  0086): "inside" extends without limit along the container's up axis (the instructions state it), so a toppled or
  tilted container can count objects as outside or inside; `object_upright` has no support term (an object in free fall
  passes); `is_supported_on_surface` accepts a mug lying on its side as "standing". `tools_picking_drill`'s term names the left bin while the drill starts in the
  right bin; the instruction says so (2026-10-14).
- Contact can make the physics diverge (joint readings of 1e6 and more, objects thrown off the table) after a grasp
  that looks ordinary; in standard mode that episode is lost (board 0086 saw it once in about 350 trials). A
  privileged `s.reset()` does not restore the start bit for bit; the verifier replays in a fresh process.


## Re-grading recorded trials (2026-10-14)
`scripts/robolab/regrade.py JOBS_DIR ... [--parallel N] [--cache-volume V] [--out regrade.jsonl]` re-grades recorded
trials under the current success term without re-running them. It finds every RoboLab trial in a Harbor jobs tree and
reads its recorded trajectory (privileged: `artifacts/app/output/trajectory.npz`; standard: the sidecar's
`trajectory.npz`, or its `journal.f64`) and its recorded verdict. It replays each trajectory once, in a fresh Isaac
process, with the current task's own tooling copy. At every control step it watches RoboLab's upstream term with the
one-finger contact (the old verdict) and the current term (the new verdict, settle hold included), and reports where
each first held.
- **Same host class.** A trial is graded on the host it ran on (Grading and determinism). The tool prints the host's CPU
  and GPU and flags a trial `inconclusive` when its recorded success does not reproduce under the old rule here.
- **Standard trials are conservative.** Under the current rule an early success would not have ended the episode, and
  the agent could still have released the object; the label is "re-graded under 2026-10-14 rules (conservative)".
- **Privileged trials are close to exact.**

## Change log
- 2026-10-17 (owner, boards 0150/0151): standard modes graded by the live episode; no grading replay; video by the sim
  service during the live episode (`live.mp4`, a frame every 3 control steps). The start-state check moved to the
  episode's start (`instance_mismatch` = a give-up as infra before serving). Collect hook 15000 s -> 3600 s. The `main`
  kill hook (`kill -9 -1`) runs before the sim's (PROTOCOL H.4). Privileged tasks unchanged. The 53 standard task dirs
  regenerated in place (new DIGESTs; instruction: the Grading sentence only).

## Licences
RoboLab: Apache-2.0 (code and assets); Isaac Lab: BSD-3-Clause on GitHub, its pip wheels and Isaac Sim 5.1 are NVIDIA
proprietary software (no redistribution), hence BUILD_ONLY.

## Standard-mode service details (moved from STANDARD_MODE.md, 2026-10-14)

Resume class `exact` (Isaac, CPU PhysX: the resumed service is a fresh process, whose first replay is bit-exact).

Its service states no `max_frames_per_call` yet.

A resume replays at ~20 steps/s. Grading (since 2026-10-17): the service judges the live episode, dumps it and exits; the hook writes `final.json` from it, with no replay (two fresh-process replays before).

Known issue: per-call state hashing on Isaac is new with crash recovery; its PRs re-check `live_matches_replay`.

Per-simulator notes (former STANDARD_MODE §16):

| | |
|---|---|
| simulator | Isaac Lab 2.3 |
| rows streamed at | 15 Hz control (8 substeps) |
| `joint_position` | 8: 7 joints + binary gripper (switched) |
| `ee_pose` | 8, closed-loop differential IK, fingertip-centre frame |
| cameras | `egocentric_mirrored_camera`, `over_shoulder_left_camera` (static), `wrist_cam` |
| depth | Isaac `distance_to_image_plane` |
| `/kinematics` | numpy model of the USD joints (7) |
| proprio columns (2.0 → 2.2) | 16 → 32 |
| grading replays | none since 2026-10-17 (graded by the live episode; two fresh processes before) |
| resume class (STANDARD_MODE §13.1) | `exact` |

Measured scene builds (former STANDARD_MODE §13.4; episode `start` minus the end of Harbor's environment setup, from standard-mode trials on the laptop, RTX 4090 laptop GPU, 32 GB: a lower bound of the build):

| benchmark | measured | build | note |
|---|---|---|---|
| RoboLab | 13 families (20 trials) | 98–217 s | default enough |
