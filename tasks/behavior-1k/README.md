# BEHAVIOR-1K

## Overview

BEHAVIOR-1K household activities for the R1Pro mobile bimanual robot, on OmniGibson 3.9.2 / Isaac Sim 5.1 (the stack
the 2026 BEHAVIOR Challenge pins). All 100 tasks of the 2026 challenge, each in two modes: 200 task directories,
`behavior-<family>-i00-privileged` and `behavior-<family>-i00-standard`. Both modes of a task use the same frozen scene
instance (the challenge's public_test instance 301) and the same success rule: the activity's official BDDL goal,
held for 1 s with the named objects released and at rest.

- **privileged**: the agent has the full simulator through `/opt/tools/rcb_behavior.py` (`Session`: the frozen instance,
  thin primitives, the robot's cameras, recording, unlimited resets) and hands in one replayable trajectory, which the
  verifier replays open-loop.
- **standard**: the simulator runs in a `sim` sidecar; the agent gets only the client (and the same service as MCP
  tools): the robot's cameras and proprioception, one episode, no reset, no object poses, no success signal.

The task directories are the deliverable; the tooling that built them is kept outside this repository.

Quick start (after the one manual step below, the dataset):
```bash
export RCB_BEHAVIOR_DATA=/path/to/behavior-data
harbor run -d embodied-first-exam@all -p tasks/behavior-1k -a codex -m openai/gpt-6-astra
```

### Before you run

1. **Host.** Linux x86_64 with Docker (BuildKit, Docker 23 or later), the NVIDIA Container Toolkit and an RTX-class
   NVIDIA GPU (Isaac Sim needs one even headless; PhysX runs on the CPU). About 13-16 GB of RAM per Isaac process (one
   simulator at a time on a 32 GB host). Disk: about 30 GB for the image and 40 GB for the dataset.
2. **The dataset (once per host; licence: non-commercial academic research only, no redistribution).** BEHAVIOR-1K's
   own downloader, run in the public base image, prints the BEHAVIOR Data Bundle licence and asks you to accept it
   (type `y`), then fetches the data anonymously from the public Hugging Face dataset `behavior-1k/zipped-datasets`
   (about 32 GB) and installs the decryption key. No account, token or GPU is needed:
   ```bash
   export RCB_BEHAVIOR_DATA=/path/to/behavior-data && mkdir -p "$RCB_BEHAVIOR_DATA"
   docker run --rm -it -e OMNIGIBSON_DATA_PATH=/data -v "$RCB_BEHAVIOR_DATA":/data \
     docker.io/stanfordvl/behavior:3.9.2@sha256:2702900192741904e69a573aa7869ea51c592586f9791050796efc37faa893fb \
     python -m omnigibson.utils.asset_utils \
     --download_omnigibson_robot_assets --download_behavior_1k_assets --download_2026_challenge_task_instances
   ```
   The directory then holds `omnigibson-robot-assets/` (3.8.2), `behavior-1k-assets/` (3.9.0),
   `2026-challenge-task-instances/` and `omnigibson.key`. Export `RCB_BEHAVIOR_DATA` in every shell that runs
   `harbor run`: every service that runs the simulator (privileged `main` and verifier, standard `sim`) mounts it
   read-only at `/data`, and `docker compose` refuses to start a BEHAVIOR task without it.
3. **The simulator image builds itself.** The task Dockerfiles carry the recipe of `images/behavior/Dockerfile`
   between `# >>> images/behavior/Dockerfile` and `# <<< images/behavior/Dockerfile`: the official
   `stanfordvl/behavior:3.9.2` by digest plus ffmpeg from a dated Ubuntu snapshot (the package state checked against
   `images/behavior/dpkg.lock`). The first trial on a host pulls the 14.7 GB base and installs ffmpeg (about 20 min);
   later trials reuse it. The image contains NVIDIA Isaac Sim and Omniverse Kit, so no public copy exists: our prebuilt
   copy `ghcr.io/mll-lab-nu/efe-private:behavior-<images/behavior/VERSION>` is private and serves only as the build
   cache (compose `build.cache_from`); without access the build goes on from public sources. `images/behavior/BUILD_ONLY`
   lists the licences and the data it needs.

The tooling and the graders come from the public files image `ghcr.io/mll-lab-nu/efe:behavior-files-<version>`
(`images/behavior-files/FILES.json` pins it by digest), built from `embodied_first_exam/benchmarks/behavior-1k/`
(`rcb_behavior.py`, `r1pro_primitives_eval.yaml`, `privileged/grade.py`, `standard/grade.py`, `sim/server.py`,
`sim/finalize.sh`); the task Dockerfiles take each file with `COPY --from=<image@digest>`, and the task dirs carry no
copy. A changed file needs a new image version and the new digest in every task.

## Upstream and license

- Upstream: BEHAVIOR-1K, [StanfordVL/BEHAVIOR-1K](https://github.com/StanfordVL/BEHAVIOR-1K) v3.9.2 (tag commit
  `b197991`), the release in the base image `stanfordvl/behavior:3.9.2` (pinned by digest). Citation: Li et al., 2024,
  "BEHAVIOR-1K: A Human-Centered, Embodied AI Benchmark with 1,000 Everyday Activities and Realistic Simulation",
  arXiv:2403.09227. Project page: https://behavior.stanford.edu/.
- Code: OmniGibson and bddl (including the BDDL activity definitions, `bddl3/bddl/activity_definitions/<task>/problem0.bddl`,
  at `/behavior-src/bddl3/` in the image): MIT License.
- Data: the BEHAVIOR Data Bundle (scenes, objects, robot assets, the 2026 challenge task instances), under the BEHAVIOR
  Data Bundle End User License Agreement: **non-commercial academic research use only (NC)**, no redistribution, use
  only within OmniGibson. It is mounted at run time and never copied into an image or this repository.
- NVIDIA Isaac Sim 5.1 and Omniverse Kit: NVIDIA proprietary licence terms (no public copy), accepted when the image is
  built.

## Changes from upstream

- **Success rule.** Upstream's challenge evaluator ends an episode at the first control step on which the BDDL goal
  holds (OmniGibson's `PredicateGoal`). Here success also needs the goal to hold for 30 consecutive control steps (1 s
  of simulated time; `REST_STEPS`), with no goal object attached to a gripper by assisted grasping and every goal
  object's base link slower than 0.05 m/s (`REST_SPEED_M_S`) on each of them. The goal objects are the BDDL objects
  the `:goal` names, by instance or through a quantifier's category (wildcard instances included), the robot
  excluded; a substance (particle system) has no pose and is skipped; a tool the goal does not name may stay in the
  hand. When the actions run out (a trajectory's last row; a standard episode ended by `/finish` or the time limit), the
  robot holds its last command with the base still for up to 150 control steps (5 s, `SETTLE_STEPS`), and a success in
  that window counts. The BDDL goals themselves are the challenge's and unchanged.
- **No step budget.** The challenge's timeout (1.5 times the mean length of the human demonstrations) is lifted to a
  runaway guard of 200,000 control steps (`MAX_STEPS`, 1.85 h of simulated time). The privileged grader accepts at
  most 40,000 rows.
- **Falls.** The episode ends as a failure when the robot has fallen over: OmniGibson's own `Falling` termination
  condition (used by its navigation tasks; `BehaviorTask` has only `Timeout` and `PredicateGoal`) with its defaults,
  on the R1Pro's `base_link`: the base more than 0.03 m below the floor, or its up axis tilted more than 41.4° from
  vertical, held for 300 consecutive control steps (10 s; `FALL_*`, `FallWatch`). A short topple that is over within
  the hold never counts (the longest recorded lasted 4.3 s); a success on the same step stands.
- **Simulator breakdown.** Checked on the robot every control step and on the goal objects every 30 (`BREAKDOWN_*`): a
  non-finite robot state, the robot or a goal object farther than 10 km from the origin, or the base faster than
  100 m/s end the episode as a failure (`sim_breakdown` = 1, a 0). A state read that fails is no evidence and the
  check stands down.
- **Replays that agree across processes.** OmniGibson iterates over Python sets of simulator objects every control
  step (object states per state type, transition rules and their candidate sets); without `__hash__` the order follows
  memory addresses, which differ between processes, so non-commuting updates (heating, slicing, cooking) diverged
  between fresh replays. The tooling hashes every prim and particle system by its unique name and every rule by its
  class name (crc32; `_stable_hashes()`) before the scene loads, and every simulator process runs with
  `PYTHONHASHSEED=0`.
- **`s.status()` changes nothing.** Its partial-goal count (the challenge's q_score) evaluates the predicates, which
  fills OmniGibson's object-state caches; `status()` restores them afterwards, so calling it does not change later steps.
- **Frozen instance.** The full simulator state after the challenge's own `Evaluator.load_task_instance` and its hash,
  in `environment/`, `tests/` and the standard sidecar. Another host may rebuild it within the pose tolerance but not
  bit-exactly (`instance_exact` = 0, `instance_ok` = 1); grading needs `instance_ok`.
- **Read-only sources.** The privileged agent's container mounts `/behavior-src` and `/opt/tools` read-only (a volume
  of the trial filled from the image); the robot assets are in the read-only dataset mount.
- Kept from upstream's evaluator: transition rules on, PhysX on the CPU, partial scene loading (the task's rooms), the
  challenge's disabled transition rules (`ToggleableMachineRule`, `MixingToolRule`, `CookingSystemRule`), the R1Pro
  robot config of the challenge with the primitives controller (`r1pro_primitives_eval.yaml`).

## Interface

The floor is the plane z = 0 (BEHAVIOR's houses); quaternions are XYZW (OmniGibson's convention). Control runs at
30 Hz with 120 Hz physics. An action has 25 entries: base (3: x, y, yaw position targets in the robot's own frame,
re-applied every step, so a per-step displacement), trunk (4), left arm (7), left gripper (2), right arm (7), right
gripper (2); trunk, arm and gripper entries are absolute joint targets. Grasping is assisted: a closing gripper holds
what it touches and lets go when both fingers are commanded open.

### Privileged

- `/opt/tools/rcb_behavior.py` (`from rcb_behavior import Session`): `Session(<task>, instance="/app/instance.json")`
  launches Isaac and loads the frozen scene (about 3 min); `reset()`, `primitives()` (thin wrappers: joint moves, a
  straight-line base drive, cuRobo IK moves without collision checking, gripper commands, object and robot poses),
  `objects()`, the robot's cameras (RGB, depth, calibration), `robot_spec()`, `kinematics()`, `step(action)`,
  `record_start()` / `record_stop()`, `status()`, `settle()`, `replay(actions)`, `save_trajectory()`, video helpers,
  and the OmniGibson robot, environment and objects themselves. Task-level skills (grasp, place, navigate) are not in
  the tooling.
- Deliverable: `/app/output/trajectory.npz` (`actions` (T, 25), one row per control step, at most 40,000 rows; `task`).
  The replay CLI does what the grader does: `python /opt/tools/rcb_behavior.py replay --task <task> --instance
  /app/instance.json --traj /app/output/trajectory.npz`.
- Self-reported cost: every Session appends to `/app/output/rcb_session_log.jsonl` (sessions, resets, steps, records,
  replays), copied into `reward.json` as `agent_*` fields with `agent_cost_self_reported` = 1.

### Standard

The adapter is `environment/sim/server.py` (from the files image) over the standard layer of
`embodied_first_exam/standard/` (wire protocol `eai-standard/3.0`); the endpoints are also MCP tools (`efe-robot`).

| | |
|---|---|
| `joint_position` | 25 columns (base per-step targets in the robot frame, trunk, arms, grippers), streamed at the 30 Hz control rate; `dt` a whole number of 1/30 s control periods |
| `ee_pose` | 16 columns (left first, xyz + xyzw), cuRobo IK for both end effectors per row, base still |
| cameras | the head camera and two wrist cameras, 224×224, moving with the robot; OmniGibson `depth_linear` on request; a frame's `extrinsic_cv` is the pose it was rendered with |
| `/kinematics` | a numpy model of the articulation (trunk + arms), cuRobo fallback; base frame unless `base_pose` is given |
| proprioception | 121 columns |
| `/spec` | `max_control_steps` (the runaway guard) and the episode's end conditions |
| images per call | at most 5412 (`max_frames_per_call`) |

Requests are checked before anything runs: a wrong type or an out-of-range `dt`, `seconds`, `video_fps` (1-30),
`cameras`, `note`, `interpolate`, `video` or `depth`, a zero `ee_pose` quaternion or a position beyond 1000 m is a 400.
Not given: object poses, the scene layout, the success signal, resets. Standard tasks never state where things are in
the world (`ci_checks/check-world-frame-texts.sh`); the floor convention above defines the frame.

Crash recovery: the service journals every control step and resumes the same episode after a restart; resume class
`approx` (OmniGibson declares rollouts nondeterministic): a state-hash mismatch after the journal replay is recorded
and the episode continues unless a TCP is more than 0.05 m from its checkpoint; a replayed episode that ends before the
logged one did is `resume_failed` (`infra_error`). Startup watchdog `RCB_STARTUP_TIMEOUT_S` = 1800 s (scene builds
measured 130-519 s, plus about 4 min to compile shaders into the trial's cold Kit cache).

## Grading

The pass condition is the success rule above on the task's BDDL goal (the goal is read from
`bddl3/bddl/activity_definitions/<task>/problem0.bddl`; BDDL reads only the first expression of `:goal`). The reward is
1 or 0; the challenge's q_score (fraction of satisfied goal conditions) is reported in `reward.json`, never graded.
Each task's README states its goal in plain words.

- **Privileged.** `tests/grade.py` replays `trajectory.npz` from the frozen instance up to 3 times
  (`[metadata] replays`), each in a fresh process (an in-process reset is approximate; fresh replays are not always
  bit-identical), with the 5 s settle window after the last row, and stops at the first replay that succeeds; any such
  replay with `instance_ok` is a success (`replays_succeeded`, `success_replay`). The graded replays run with tiny
  cameras and no video; a video replay runs after the verdict and never decides anything (`video_replay_matches`).
  Agent failures (0): `missing_trajectory`, `bad_trajectory` (not an npz, pickled or object arrays, no `task` or
  `actions`, a wrong shape, non-finite values, more than 40,000 rows), `wrong_family`, a fall, a breakdown.
  Infrastructure (`infra_error` = 1, `grader_error` = 1): `instance_ok` = 0 (the frozen scene did not rebuild here,
  decided before the first action), a replay process that dies (`replay_failed`) or runs out of time
  (`replay_timed_out`). Each replay gets `min(28000 s, max(3600 s, 1200 s + rows / 1.5))`; `[verifier] timeout_sec` =
  113800 s covers three capped replays, the video replay and 30 min.
- **Standard.** Graded by the live episode; nothing replays it. The sim service judges the success rule at every
  control step and records it without ending the episode or showing it. The episode ends at the agent's `/finish` or
  when the time limit is up; the service then runs the 5 s settle window on the live simulator (stopping once the rule
  holds; steps that held before count) and the end state's verdict is the episode's (`settled_success`). A fall or a
  breakdown (also in the window) or a simulator error raised by the agent's call is a 0; at the runaway guard the
  episode is judged as it stands. `finalize.sh` writes `final.json`; `tests/grade.py` transcribes it, with
  `infra_error` = 1 when it is missing, unreadable or not finalized, and for `sim_crashed`, `resume_failed` and
  `instance_mismatch`; `sim_crashed_on_call` is the agent's 0. `[[verifier.collect]] timeout_sec` = 23400 s: the end
  (up to 2 h through a resume) + a video-only render when the live video is missing (up to 4 h) + 30 min.
- Video: privileged `replay.mp4` from the video replay; standard `live.mp4`, recorded during the episode (the robot's
  three cameras, every third control step).

What some official goals do not require (the BDDL goal is the judge, as in the challenge):

- `loading_the_car` lists `(not (open car))` after the goal's `(and ...)`, so the car may stay open.
- `carrying_in_groceries` checks only `electric_refrigerator.n.01_1` for being closed, not the kitchen's other
  refrigerators; `tidying_bedroom` checks only the first sandal next to the bed (the second next to the first);
  `sorting_vegetables` does not need three different bowls; `clearing_food_from_table_into_fridge` does not need the
  two foods in different tupperwares.
- `stacking_wood` only needs every log to touch another log; `laying_tile_floors` only needs the tiles on the floor,
  each next to another; `hiding_Easter_eggs` only needs the eggs on the lawn next to one tree and out of the basket.
- `freeze_fruit` does not need the fruit frozen; `cook_hot_dogs`, `cook_bacon` and `cook_a_frozen_pie` need only
  `cooked` (the object's highest temperature so far), from any heat source; `chopping_wood` needs only the eight half
  logs to exist; `make_pizza` only a pizza on the cookie sheet.
- `contains` and `covered` are true with a single particle (`chop_an_onion`, `make_microwave_popcorn`, `cook_cabbage`,
  `spraying_for_bugs`, `spraying_fruit_trees`); the cleaning tasks need `not covered`, however the substance leaves.

## Tasks

100 families, all on instance 301 (`[metadata] instance_seed`), each with a privileged and a standard task:
assembling_gift_baskets, attach_a_camera_to_a_tripod, boxing_books_up_for_storage, boxing_food_after_dinner,
bringing_in_wood, bringing_paper_to_recycling, bringing_water, can_meat, canning_food, carrying_in_groceries,
carrying_out_garden_furniture, chop_an_onion, chopping_wood, clean_a_keyboard, clean_a_patio, clean_a_trumpet,
clean_boxing_gloves, clean_up_broken_glass, clean_up_your_desk, clean_your_rusty_garden_tools,
cleaning_up_branches_and_twigs, cleaning_up_plates_and_food, clearing_food_from_table_into_fridge,
collecting_aluminum_cans, collecting_childrens_toys, composting_waste, cook_a_brisket, cook_a_frozen_pie, cook_bacon,
cook_broccolini, cook_brussels_sprouts, cook_cabbage, cook_hot_dogs, dispose_of_batteries, dispose_of_glass,
freeze_fruit, freeze_pies, getting_organized_for_work, halve_an_egg, hanging_pictures, hiding_Easter_eggs,
installing_a_fax_machine, installing_a_modem, installing_a_scanner, installing_smoke_detectors, laying_tile_floors,
loading_the_car, make_cabinet_doors, make_gift_bags_for_baby_showers, make_microwave_popcorn, make_pizza,
make_rose_centerpieces, moving_boxes_to_storage, organizing_art_supplies, organizing_school_stuff,
outfit_a_basic_toolbox, packing_meal_for_delivery, picking_up_toys, picking_up_trash, polishing_shoes,
preparing_lunch_box, put_together_a_basic_pruning_kit, putting_away_Halloween_decorations, putting_away_toys,
putting_dirty_dishes_in_sink, putting_dishes_away_after_cleaning, putting_shoes_on_rack,
putting_up_Christmas_decorations_inside, re_shelving_library_books, rearrange_your_room,
rearranging_kitchen_furniture, scrubbing_bathroom_floor, set_up_a_coffee_station_in_your_kitchen, setting_mousetraps,
setting_the_fire, setting_the_table, setup_a_bar_for_a_cocktail_party, slicing_vegetables, sorting_books_on_shelf,
sorting_bottles_cans_and_paper, sorting_household_items, sorting_vegetables, spraying_for_bugs, spraying_fruit_trees,
stacking_wood, store_batteries, store_honey, store_produce, storing_food, sweeping_garage, thawing_frozen_food,
tidying_bathroom, tidying_bedroom, tidying_living_room, turning_on_radio, turning_out_all_lights_before_sleep,
unloading_the_car, vacuuming_floors, wash_a_baseball_cap, wash_dog_toys.

The goals span placing and containing objects, articulated objects (`open`), devices (`toggled_on`), heat (`cooked`,
`frozen`, `on_fire`), cutting and dicing (`real`: halves, diced pieces and cooked food that OmniGibson's transition
rules create during the episode), particles (`filled`, `contains`, `covered`) and attachment (`attached`), in
houses, offices, a restaurant and outdoor scenes.

| family | reference solution |
|---|---|
| picking_up_trash, putting_shoes_on_rack | `partial`: human-written reference solutions on the frozen task-level primitives `solution/rcb_behavior_ref.py` (privileged); the standard oracle streams the privileged oracle's joint targets through the client |
| the other 98 | none (`oracle = "none"`); solvability evidence in each task's `oracle_evidence` (the challenge's human teleoperation demonstrations of the activity in the same scene model, or a successful agent trial) |

## Others

- **Time.** 7200 s for every task of both modes (each task's own `[agent] timeout_sec`). Every Python process pays an
  Isaac launch and scene load (about 2-3 min with a warm Kit cache, about 4 min more on the first launch of a trial),
  and the simulator runs 7-18 control steps/s depending on the host.
- **Kit cache: one per trial.** Isaac keeps shaders and generated Python in its Kit cache (`/cache`). Every compose file
  names its cache volume without a fixed `name:` (`rcb_behavior_cache` for the agent, `rcb_behavior_cache_trusted` for
  the verifier and the standard sidecar), so side-by-side trials never share it and Harbor's teardown deletes it.
- **GPU.** The compose files reserve one GPU (`count: 1`), which Docker serves with the host's first GPU. torch /
  OpenMP pools are capped at 8 threads in every service that runs the simulator.
- **Network.** The agent reaches the model APIs and the package registries only (`[agent] network_mode =
  "allowlist"`); nothing in a BEHAVIOR container needs the network at run time. The standard `sim` service shares the
  agent's egress namespace (the allowlist); both verifiers run with no network.
- **Known issues.** While the robot moves, a frame shows the scene 2 control steps before its `frame_step` (renderer
  latency). `turning_on_radio`: the radio shows no visual change when it is on, so a standard-mode agent cannot see its
  success. Goals that create objects (`real`) or clean surfaces (`not covered`) depend on OmniGibson's transition rules
  and particle states; every particle system these tasks use is a macro system (no GPU dynamics needed).
- **Tooling files.** Privileged `/opt/tools/rcb_behavior.py` and `/tests/rcb_behavior.py`; the standard sidecar's
  `server.py`, `finalize.sh`, `rcb_behavior.py` and the robot config; `solution/rcb_behavior_ref.py` for the reference
  solutions only. Every copy is byte-identical across the benchmark and the files image (`check-tooling-identity.sh`).
