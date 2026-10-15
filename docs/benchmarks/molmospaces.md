# MolmoSpaces

The benchmark episodes Ai2 uses to evaluate robot policies zero-shot in unseen houses: picking, placing, articulated
objects and navigation, on a fixed-base arm and a mobile manipulator.

| | |
|---|---|
| upstream | [Ai2 MolmoSpaces](https://github.com/allenai/molmospaces) (molmo-spaces 0.2.9, Apache-2.0), packages `molmospaces-bench-v2/20260415` |
| simulator | `molmospaces`: MuJoCo 3.5.0, CPU physics, EGL rendering on a GPU (OSMesa without one, ~15× slower) |
| robots | `franka-robotiq-2f85` (Franka FR3 + Robotiq 2F-85 on a fixed base, the DROID setup); `rainbow-rby1` (RB-Y1: holonomic base, 6-joint torso, two 7-joint arms) |
| score | upstream's `judge_success()` on the state at the episode's end |
| tasks | 8 families × 2 modes: `tasks/molmospaces-<family>-i00-privileged` and `-standard` (`eai-standard/2.2`) |
| image | `ghcr.io/mll-lab-nu/eai-molmospaces:0.2.3` (`images/molmospaces/`, ~1.8 GB of assets) |
| oracle | none: upstream's planners and grasp files are not shipped; a positive example per family (`oracle_evidence`), human review in PR #47 |

| family | upstream package | robot, control period | variants | kept episode (i00) | horizon |
|---|---|---|---|---|---|
| pick | `procthor-objaverse/FrankaPickHardBench` | Franka, 66 ms | AI2-THOR / Objaverse object | #387: a white light switch plate | 303 steps (20 s) |
| pick-and-place | `procthor-objaverse/FrankaPickandPlaceHardBench` | Franka, 66 ms | AI2-THOR / Objaverse object | #134: a small white bird figurine into a black bowl | 606 (40 s) |
| pick-and-place-next-to | `procthor-objaverse/FrankaPickandPlaceNextToHardBench` | Franka, 66 ms | AI2-THOR / Objaverse object | #89: a red VHS tape beside a soap bottle | 455 (30 s) |
| pick-and-place-color | `procthor-objaverse/FrankaPickandPlaceColorHardBench` | Franka, 66 ms | AI2-THOR / Objaverse object | #26: a stopwatch into the red bowl | 606 (40 s) |
| open | `ithor/FrankaOpenHardBench` | Franka, 66 ms | drawer / hinged door | #49: a cabinet's hinged door (any cabinet in the room counts) | 455 (30 s) |
| close | `ithor/FrankaCloseHardBench` | Franka, 66 ms | drawer / hinged door | #51: a cabinet's hinged door | 455 (30 s) |
| navigate-to | `holodeck-objaverse/NavToObjDataGenConfig` | RB-Y1, 200 ms | one target / several (nearest counts) | #94: a bed two rooms away | 500 (100 s) |
| open-door | `procthor-10k/rby1_benchmarks/door_opening_benchmark` | RB-Y1 (RBY1M), 100 ms | push / pull | #0: a door to pull | 400 (40 s) |

## Instances (`scripts/molmospaces/make_instances.py`)
Per family, the first episode in the package's order that passes every filter ships as `i00` (no model's results enter
the choice; `keep` in `families.json` records it, `make_instances.py` checks it):
- **Valid:** no public MolmoBot trajectory of the house (`allenai/molmobot-data`, val); upstream builds every listed
  object; not done at t = 0; no asset whose licence forbids commercial use (the image redistributes them).
- **Named unambiguously:** no identical copy of the target or receptacle, and no other object of a named object's
  WordNet synset within 1 m of it (colour's second receptacle differs by colour, by design); navigation: every
  candidate target has the target's synset.
- **Hard**, measurable and the same for every model:

| families | rule |
|---|---|
| pick, pick-and-place(-next-to, -color) | at least 5 other objects within 30 cm of the target |
| open, close | upstream's Hard packages: arm start posture randomised (±0.26 rad per joint, wrist ±90°), base up to ±30° off facing the fixture, 5 randomised cameras |
| navigate-to | the nearest target at least 8 m from the base and out of `head_camera`'s view at t = 0 |
| open-door | none beyond the package |

The instance is the upstream episode with `source` (its expert trajectory's path) removed; navigation's text is upstream
`NavToObjTask`'s own. Assets: Objaverse `20251016_from_20250610`, the version the benchmark was made with (0.2.9 defaults
to `20260131`), pinned with upstream's `MLSPACES_PINNED_ASSETS_FILE`; navigation uses the Holodeck package (the
ProcTHOR-10k one misses objects on 0.2.9's scene version).

## Upstream decides the outcome
- `scripts/molmospaces/shared/rcb_molmospaces.py`, copied unchanged into every task, builds the frozen episode through
  upstream's evaluation path (`JsonEvalRunner` → `JsonEvalTaskSampler` → `task.reset`, action noise off). One control
  step = one upstream `Task.step` with every move group's targets; each step also polls every camera, as upstream's
  pick-and-place success reads that history. Physics, controllers, kinematics and the success checks are upstream's.
- The episode ends at upstream's `is_done()` (the horizon) or when the agent ends it: standard mode's `done` ends it at
  once (upstream's `"done": True` action still runs that row's step), privileged mode where its trajectory ends. Success
  is judged at the end (`terminate_upon_success = False`, upstream's evaluation default).
- Rates: the Franka's from upstream's evaluation config; the RB-Y1's from its data-generation configs (it has no
  evaluation config).
- One loader change: `set_joint_values` raises unless the articulated target has a grasp file; it only checks that the
  file exists, so the check answers "exists" while the episode is built.

## Modes

| mode | the agent gets | resets | graded |
|---|---|---|---|
| privileged | `Session`: full state (`s.state()`, `s.model` / `s.data`), any camera, upstream's kinematics, reward and success code | unlimited | `tests/grade.py`: `trajectory.npz` replayed in two fresh processes; both succeed with equal final hashes |
| standard | `joint_position` (Franka 8, RB-Y1 25) and `done`; the robot's cameras (not the third-person follower), proprioception, `/kinematics` | none (D1) | `finalize.sh` replays the recorded rows twice; success = live ∧ replay ∧ deterministic |

Standard mode's texts name objects and the goal only (D7, `scripts/molmospaces/ci/advisory-world-frame.sh`); the robot's pose and
camera calibration come from the service, object poses never. Both graders check that each replay starts in the
instance's t = 0 state (else `grader_error`, with `infra_error`); a third replay renders `replay.mp4` after the verdict. Crash recovery:
resume class `exact` (`scripts/molmospaces/kill_test.sh`). Budget: each task's own `[agent] timeout_sec` (PROTOCOL §2.12, [`../CUTOFFS.md`](../CUTOFFS.md); 3600 s on
2026-10-11), stated by the closing `## Time limit` section of every instruction; no step limit beyond the horizon.

Tests without a simulator: `scripts/molmospaces/tests/test_ms.py` (run as a script; numpy): both graders, `finalize.sh` with
stand-in replays and the real `server.py` on the real shared layer with a stub Session.

What is not the agent's failure is flagged, and a reward is always written (2026-10-10). Standard `infra_error = 1`: no
`final.json` (`missing_log`), an unreadable one (also `grader_error`), an unfinished one (`finalized` 0: the collect hook
did not write its verdict; these three used to be the agent's 0 or no reward at all), a give-up after crashes between
calls or a failed resume, a service that did not end its episode for the hook, a replay process without a result
(`replay_failed`), replays that did not start in the t = 0 state (`instance_mismatch`); a give-up after crashes during a
call stays the agent's failure. `finalize.sh` writes `final.json` whole and renames it into place, and ends a replay at
500 s or at the hook's own deadline (1740 s of its 1800 s), whichever comes first. Privileged: a file that cannot be read
as a trajectory (not an npz, a pickled or non-numeric `actions`) is `bad_trajectory` (was `grader_error`). The service
checks a request completely before anything moves: a null or wrongly typed `dt`, `seconds`, `cameras`, `note`, `video`,
`interpolate` or `type` is a 400 (a null `dt` or `seconds` and a non-string `note` used to be a 500 that ended the
episode). `get_obs(seconds=...)` runs whole control steps (the request rounded to the control period, 66 ms for the
Franka tasks) and `meta["seconds"]` is what ran, not what was asked for. The only step limit is upstream's horizon, which
the instruction and `/spec` (`max_control_steps`, `episode`) state.

## Image and generator
- `images/molmospaces/prepare_assets.sh`, then the image build: the measured environment (`requirements.txt`,
  `--no-deps`); upstream's scripted experts replaced by raising stubs in the same layer (`scrub_experts.py`); the assets
  the instances open under `strace` (everything else deleted, no grasp file); every instance's t = 0 hash checked again
  without network. Upstream's generic A* and grasp-generation library code stay installed. Licences: scenes and
  AI2-THOR objects CC BY 4.0; Objaverse objects ODC-BY 1.0 and each its creator's CC BY / BY-SA / CC0, listed with
  their attributions in the image's `/opt/molmospaces/ATTRIBUTION.md` (the build fails on a non-commercial one).
- `python3 scripts/molmospaces/mk_tasks.py [--check]` writes all 16 task dirs from `families.json`, `instances/`,
  `template/<mode>/`, `shared/` and `scripts/eai_standard/`; re-running leaves `git diff tasks/` empty.

## Run

```bash
harbor run -p tasks/molmospaces-pick-i00-standard -a codex -m openai/gpt-6-luna --env-file .env
harbor run -p tasks/molmospaces-pick-i00-privileged -a nop      # scores 0
```
Agent, provider and effort settings: docs/RUNNING.md. Results are not kept in this repository (PROTOCOL D3): runs, videos and per-run READMEs are on
the results site.

## Standard-mode service details (moved from STANDARD_MODE.md, 2026-10-14)

Resume class `exact` (MuJoCo, CPU physics).

Its service states no `max_frames_per_call` yet.

Grading: the service dumps the episode, exits, and the hook replays it in two fresh processes.

Per-simulator notes (former STANDARD_MODE §16):

| | |
|---|---|
| simulator | molmo-spaces 0.2.9, MuJoCo 3.5.0 |
| rows streamed at | Franka 15.15 Hz (33 substeps); RB-Y1 5 Hz (navigation, 100) or 10 Hz (door, 50) |
| `joint_position` | Franka 8: 7 joints + Robotiq command (0–255); RB-Y1 25: base x, y, θ (world) + torso 6 + arms 14 + two gripper forces |
| `ee_pose` | not offered (`not_yet`) |
| cameras | Franka: wrist and shoulder (moving), three randomised static; RB-Y1: head + two wrist cameras (moving) |
| depth | MuJoCo depth buffer |
| `/kinematics` | upstream's `MlSpacesKinematics` on the robot's MuJoCo model (Franka 7, RB-Y1 23 with the base) |
| proprio columns (2.0 → 2.2) | 2.2 only: 29 (Franka), 85 (RB-Y1) |
| grading replays | two fresh processes |
| resume class (STANDARD_MODE §13.1) | `exact` |

Measured scene builds (former STANDARD_MODE §13.4; episode `start` minus the end of Harbor's environment setup, from standard-mode trials on the laptop, RTX 4090 laptop GPU, 32 GB: a lower bound of the build):

| benchmark | measured | build | note |
|---|---|---|---|
| MolmoSpaces | 8 families (213 trials), on a lab host (RTX 4090, 32 cores) | episode start 8–52 s after Harbor's environment setup began (median 11 s; navigate-to 33–52 s) | `RCB_STARTUP_TIMEOUT_S` = 300 |
