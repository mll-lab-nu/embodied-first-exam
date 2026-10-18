# BEHAVIOR-1K

BEHAVIOR-1K v3.9.2 (OmniGibson 3.9.2 on Isaac Sim 5.1, the stack the 2026 BEHAVIOR Challenge pins): household tasks for
the R1Pro mobile manipulator. `simulator = "behavior"`, `robot = "r1pro"`. 100 challenge tasks (the 2026 challenge's full set), each as a privileged task
`behavior-<family>-i00-privileged` and its standard twin `behavior-<family>-i00-standard`, on the 2026 challenge's
public_test instance 301: 11 tasks with a reference solution or a positive example, and 89
supplementary tasks for harder testing (below), which have neither yet.

## Prerequisites (every BEHAVIOR run)
- **The image**, built on the host: `ghcr.io/mll-lab-nu/eai-behavior:<images/behavior/VERSION>`
  is the official `stanfordvl/behavior:3.9.2` **by digest** plus a snapshot-pinned ffmpeg layer. It contains NVIDIA
  Isaac Sim and Omniverse Kit (no redistribution) and a 13.7 GB layer above ghcr.io's per-layer limit: **BUILD_ONLY**,
  never pushed. `images/behavior/BUILD_ONLY` has the build command, the licences and the data it needs.
- **The licensed dataset**, `RCB_BEHAVIOR_DATA`: the host directory with the BEHAVIOR Data Bundle
  (`omnigibson-robot-assets/`, `behavior-1k-assets/`, `2026-challenge-task-instances/`, `omnigibson.key`), downloaded after
  accepting its licence, which forbids redistribution. It is never in an image: every compose service that runs the
  simulator (privileged `main` and verifier, standard `sim`) mounts it read-only at `/data` as
  `${RCB_BEHAVIOR_DATA:?…}`, so `docker compose` refuses to start a BEHAVIOR task without it. Export it before
  `harbor run`.
- **One RTX-class NVIDIA GPU per Isaac process** (Isaac needs one even headless; PhysX runs on the CPU). The compose files
  reserve `count: 1`, which Docker serves with the host's first GPU (GPU 0).
- About 13-16 GB of RAM per Isaac process: one Isaac simulator at a time on a 32 GB host. torch / OpenMP pools are capped
  at 8 threads in every compose service that runs the simulator (uncapped they span every core of a large host and run up
  to 15× slower).

## Tasks and generator
- `scripts/behavior/mk_tasks.py` generates every task from the template twins `tasks/behavior-picking-up-trash-i00-privileged`
  and `-standard` (maintained by hand), `scripts/behavior/families.json` (the texts of each family: goal, success conditions,
  difficulty, the standard goal in words; the oracle level and its evidence: the cited positive, or the challenge's
  official human demonstrations, `"demo"`; `"added"` for a family added after the first 50, and its own `"review_pr"`
  where a later pull request reviews it; `"include"`), the BDDL problems
  `scripts/behavior/bddl/` (BEHAVIOR-1K's `bddl` package, MIT: `/behavior-src/bddl3/bddl/activity_definitions/<task>/problem0.bddl`
  in the image), the frozen instances `scripts/behavior/instances/` and the reference solutions
  `scripts/behavior/solutions/`, plus the eai-standard/2.2 layer from `scripts/eai_standard/`. A rerun reproduces the
  committed tasks; `mk_tasks.py --check` regenerates into a temporary tree and diffs. It writes every README in the
  protocol's layout and ends each task with `scripts/task_conventions.py`'s `normalize()`, like every generator.
  `scripts/behavior/goal.py` words each BDDL predicate a goal uses, with OmniGibson's thresholds. Agent results are not
  in the repository: the positives are cited by trial id, results-site log and Hugging Face replay.
- The predicate is the task's official BDDL goal (OmniGibson object states), checked at every control step; success needs
  it to hold for 1 s, released and at rest (§ Success), and the episode ends there, or as a failure when the
  robot has fallen over (§ Falls). The challenge's timeout is lifted to
  a runaway guard (time is the budget, not steps).
- Frozen instance: the full simulator state after the challenge's own instance load (`Evaluator.load_task_instance`) and
  its hash, in `environment/`, `tests/` and the standard sidecar. Another host may rebuild it within the pose tolerance but
  not bit-exactly (`instance_exact = 0`, `instance_ok = 1`); grading needs `instance_ok`.

| family | oracle | evidence (PROTOCOL §4) |
|---|---|---|
| picking_up_trash, putting_shoes_on_rack | `partial` | human-written reference solutions on the frozen task-level primitives `solution/rcb_behavior_ref.py`; the standard oracle streams the privileged oracle's joint targets through the client. They scored 1 on an earlier version of the service, collect hook, grader and oracle client (`oracle_evidence` cites the runs; picking_up_trash privileged 1 of 3) and have not been re-run on this one, hence not `full` |
| clean_up_broken_glass, collecting_aluminum_cans, composting_waste, dispose_of_glass, hiding_Easter_eggs, installing_a_scanner, stacking_wood, tidying_bedroom, turning_on_radio | `none` | a privileged model trial graded 1 by the separate verifier on an earlier version (trial id, agent log and replay in `oracle_evidence` and the README); human review per family |
| the 89 supplementary families (below) | `none` | no positive example yet: the 2026 challenge's official human teleoperation demonstrations of the activity with the R1Pro in the same scene model (the video, its duration, the number of episodes and their mean duration in `oracle_evidence` and the README); human review per family |

The labels follow one rule: `full` only when a recorded oracle run scored 1 on a byte-identical grader, frozen instance and
oracle code, with every tooling change since shown to be off the oracle and replay path. This version was validated
statically (CI, the generator's `--check`), not re-run.

**Loose official goals** (reported, the official judgement is kept): `stacking_wood` only needs every log to touch
another log (no stack; its positive pushed the logs together with the robot body); `hiding_Easter_eggs` only needs the
eggs on the lawn next to one tree and out of the basket (nothing is hidden); `laying_tile_floors` only needs the tiles on
the floor, each `nextto` another; `loading_the_car` lists `(not (open ?car.n.01_1))` outside the goal's `(and ...)`, and
BDDL reads only the first expression of `:goal`, so the car may stay open; `sorting_vegetables` needs one bowl per
vegetable group, not three different bowls; `freeze_fruit` does not need the fruit frozen; `spraying_for_bugs` and
`spraying_fruit_trees` need the plants and trunks `covered`, true as soon as particles of the substance are on them (not
"fully covered", as the challenge's instruction says); `cook_hot_dogs`, `cook_bacon` and `cook_a_frozen_pie` need only
`cooked`, from any heat source; the cleaning and washing tasks (clean_boxing_gloves, wash_a_baseball_cap,
clean_a_trumpet, clean_a_keyboard, sweeping_garage, scrubbing_bathroom_floor) need only `not covered`, however the
substance leaves. The instructions say so.

## Supplementary tasks
89 challenge tasks added for harder testing, which with the 11 make all 100 tasks of the 2026 challenge: long official
demonstrations (the challenge's teleoperators needed 80-869 s on average), a spread of skills (articulated objects, tool
use, heat, cutting, surface cleaning, particles, devices, two-handed carrying, outdoor scenes, several rooms). Their
predicates go beyond the first eleven's: `real` (objects that the simulator's transition rules create during the episode:
halves, diced pieces, cooked food, a pizza), `filled` and `contains` (particles in a container), `attached`
(hanging_pictures, the poster on a wall nail); `goal.py` words them. No reference solution was written: `oracle =
"none"`, with the official demonstrations as the solvability evidence (`demo`), reviewed per family (PROTOCOL §4); the
families with `added` in `families.json` name the pull request of their human review (`REVIEW_PR`, or
`THIRD_BATCH_PR` for `review_pr: third_batch`, in `mk_tasks.py`) in `oracle_evidence` and the README. Every instance is
the challenge's public_test instance 301, frozen with `Evaluator.load_task_instance`, its BDDL goal false at the start;
checked per batch (fresh-process reloads with an exact state hash or every object pose within tolerance, `instance_ok`;
Harbor `nop` 0 in both modes) on a sample of each batch, not on every instance.

Families: assembling_gift_baskets, attach_a_camera_to_a_tripod, boxing_books_up_for_storage, boxing_food_after_dinner,
bringing_in_wood, bringing_paper_to_recycling, bringing_water, can_meat, canning_food, carrying_in_groceries,
carrying_out_garden_furniture, chop_an_onion, chopping_wood, clean_a_keyboard, clean_a_patio, clean_a_trumpet,
clean_boxing_gloves, clean_up_your_desk, clean_your_rusty_garden_tools, cleaning_up_branches_and_twigs,
cleaning_up_plates_and_food, clearing_food_from_table_into_fridge, collecting_childrens_toys, cook_a_brisket,
cook_a_frozen_pie, cook_bacon, cook_broccolini, cook_brussels_sprouts, cook_cabbage, cook_hot_dogs, dispose_of_batteries,
freeze_fruit, freeze_pies, getting_organized_for_work, halve_an_egg, hanging_pictures, installing_a_fax_machine,
installing_a_modem, installing_smoke_detectors, laying_tile_floors, loading_the_car, make_cabinet_doors,
make_gift_bags_for_baby_showers, make_microwave_popcorn, make_pizza, make_rose_centerpieces, moving_boxes_to_storage,
organizing_art_supplies, organizing_school_stuff, outfit_a_basic_toolbox, packing_meal_for_delivery, picking_up_toys,
polishing_shoes, preparing_lunch_box, put_together_a_basic_pruning_kit, putting_away_Halloween_decorations,
putting_away_toys, putting_dirty_dishes_in_sink, putting_dishes_away_after_cleaning,
putting_up_Christmas_decorations_inside, re_shelving_library_books, rearrange_your_room, rearranging_kitchen_furniture,
scrubbing_bathroom_floor, set_up_a_coffee_station_in_your_kitchen, setting_mousetraps, setting_the_fire,
setting_the_table, setup_a_bar_for_a_cocktail_party, slicing_vegetables, sorting_books_on_shelf,
sorting_bottles_cans_and_paper, sorting_household_items, sorting_vegetables, spraying_for_bugs, spraying_fruit_trees,
store_batteries, store_honey, store_produce, storing_food, sweeping_garage, thawing_frozen_food, tidying_bathroom,
tidying_living_room, turning_out_all_lights_before_sleep, unloading_the_car, vacuuming_floors, wash_a_baseball_cap,
wash_dog_toys.

## Time budget
7200 s for every task of both modes (each task's own `[agent] timeout_sec`, written by the generator; `instruction.md`
states it once, in its closing `## Time limit` section, and the benchmark's own text says "the time limit (`## Time
limit`)"). Every Python process pays an Isaac launch and scene load (about 2-3 minutes with a warm Kit cache; the first
launch of a trial adds about 4 minutes to compile shaders into the trial's own cache, below), and the simulator runs
7-18 control steps/s depending on the host (30 Hz control), while these tasks take thousands of steps.

### Verifier time
Time limits only; the pass rules do not depend on them. The eval hosts are 8-vCPU L40S / L4 machines, on which an Isaac
start takes up to ~20 min and a replay can run below 2 control steps/s.
- **Privileged.** The grader accepts at most **40,000 rows** (`MAX_ROWS` in `tests/grade.py`; above every challenge
  timeout, `challenge_max_steps` up to 39,090, and 1.6 times the longest recorded success, 25,404 rows); the instruction
  states the cap. Each of the two fresh-process replays gets `min(28000 s, max(3600 s, 1200 s + steps / 1.5))` (1.5
  steps/s is 20 % under the slowest rate measured, 1.88; 1200 s covers the slowest start). A replay over its limit is a
  grader error (`grader_error` = 1, `replay_timed_out` = 1). `[verifier] timeout_sec` = 85800 s: the two capped replays,
  the video replay (after the verdict, with a graded replay's limit, within the verifier's remaining time:
  `VERIFIER_TIMEOUT_S`), plus 30 min.
- **Standard.** No grading replay (graded by the live episode, below); the collect hook (`environment/sim/finalize.sh`)
  waits for the episode's end and, only when the live video is missing, renders one video-only replay after the
  verdict, within `[[verifier.collect]] timeout_sec` = 23400 s (`BUDGET_S`).

## Kit cache: one per trial
Isaac keeps shaders and generated Python in its Kit cache (`/cache`). Every compose file names its cache volume without a
fixed `name:` (`rcb_behavior_cache` for the agent, `rcb_behavior_cache_trusted` for the verifier and the standard
sidecar): compose prefixes it with the trial's project name, side-by-side trials never share it, and Harbor's teardown
(`compose down --volumes`) deletes it. A scene load takes about 360 s on a cold cache and 110 s on a warm one, so each
container pays about 4 minutes once (the agent's first `Session`, the sidecar's start, the verifier's first replay; the
second replay reuses the cache). No global volume that agents of different trials could write, or that a concurrent
trial's teardown could delete. A cache can reach ~10 GB; it lives as long as the trial.

## Host notes (host-local, never committed)
- **GPU pin.** `count: 1` always gives GPU 0. A host whose BEHAVIOR GPU is another one (lab) pins it at run time with a
  host-local compose override (`device_ids` on `main` / `sim`, like lab's verifier-subnet patch), applied to its own copy
  of the tasks and written down in that host's notes, never committed.
- **Docker address pools.** A host with exhausted pools (lab) gives each trial explicit subnets (its agent environment
  through an extra compose file, its separate verifier through a patch of its copy of `tests/docker-compose.yaml`). The
  standard verifier needs no network (`no-network`).
- **Verifier network.** Both verifiers run with `[verifier] network_mode = "no-network"` (PROTOCOL H.6): Harbor denies
  the separate verifier all egress while `tests/test.sh` runs. The privileged verifier starts Isaac Sim offline and
  downloads nothing: the dataset is mounted and the image is complete.

## Network
The agent reaches the model APIs and the package registries (PyPI, apt archives), nothing else: `[agent] network_mode =
"allowlist"` with the hosts of `scripts/set_agent_egress.py`, which `mk_tasks.py` (`agent_egress`) writes into every
task. Nothing in a BEHAVIOR container needs the network at run time: the image holds Isaac Sim, OmniGibson, cuRobo and
every Python package, the scenes and robot assets come from the mounted dataset, and the EULA is accepted by an
environment variable. Open egress would allow a download of the 2026 challenge's public material for the same
activities (its teleoperated demonstrations, which a task's name locates, and its baselines).

| Service | Egress |
|---|---|
| privileged `main` (agent and its Isaac processes) | public from container start until the agent starts (the harness is installed then), the allowlist while the agent runs |
| standard `main` (agent, client only) | the same |
| standard `sim` (the simulator service) | the same as `main`: Harbor's egress control puts every compose service without a network setting of its own in one namespace, so the service's Isaac start (at container start, about 10 minutes) and a restart after a crash run with the allowlist only; public again while the collect hook runs (a video-only render, when the live video is missing) |
| `rcb_monitor` | none |
| privileged verifier | none (`no-network`) |
| standard verifier | none (`no-network`) |

Checked on L40S hosts: under the allowlist GitHub, Hugging Face and NVIDIA's Omniverse content bucket are unreachable,
the oracles give the same rewards and state hashes as with open egress, and Isaac loads the scene from the mounted
dataset alone.

## Grading and determinism
- Privileged: the verifier replays `trajectory.npz` from the frozen instance in **two fresh processes** (an in-process
  reset is approximate; the first replay in a fresh process reproduces a live run bit for bit) and needs the goal after
  both, equal final-state hashes and `instance_ok`.
- **Standard: graded by the live episode.** `success` = the live episode's success, judged by the sim service at every
  control step with the success rule below; nothing replays the episode. On the collect hook's signal (after `main`'s
  `kill -9 -1` hook has stopped the agent's processes) the signal's thread only stops the HTTP loop (Isaac steps on the
  request thread); the request thread then ends the episode (`server.py end_live`): an episode still running gets the
  success rule's settle window on the live simulator, the robot held still for up to 5 s (not journaled, not in
  `trajectory.npz`), and a goal that settles there is the episode's success (`settled_success`, `settle_steps`); a fall
  or breakdown in the window ends it as one. The service writes `trajectory.npz` (the agent's rows) and `episode.json`,
  closes the video and exits; `finalize.sh` writes `final.json` from `episode.json` (`graded_by` "live", `replays` 0).
  The frozen start is checked when the service builds the scene (the instance's state hash, else every task object's
  pose within tolerance; `Session.instance_matches`): a mismatch gives up as `instance_mismatch` (`infra_error`) before
  the agent is served. Video: recorded live (`/out/live.mp4`): the robot's three cameras at 224 px, tiled, every third
  control step (10 fps), copied in the control loop and encoded by a thread (PyAV, fragmented MP4: a crash leaves a
  playable prefix); a resume records it anew while replaying the journal. Only when it is missing or does not play does
  `finalize.sh` run ONE video-only render (the tooling's `replay --video`, `replay.mp4`) after the verdict, whose success
  and hash are not read. `[[verifier.collect]] timeout_sec` = 23400 s: the end (up to 2 h through a resume) + the video
  render when it runs (up to 4 h) + 30 min. The settle window is logged as a call (`/settle`), so a crash there counts as
  inside the agent's calls; known limit: a native crash (segfault) of the service in the window restarts the sim
  container and with it ends the collect hook running there (no finalized `final.json`: infrastructure).
- **Replays that agree.** OmniGibson iterates over Python sets of simulator objects every control step (object states
  per state type, `for obj in scene.get_objects_with_state(state_type)`; transition rules, `for rule in
  tuple(self.active_rules)`, and their candidate sets); with no `__hash__`, the order follows memory addresses, which
  differ between processes, and updates that do not commute (burning objects heating each other, slicing, cooking)
  diverge between fresh replays. The tooling hashes every prim and particle system by its unique name and every rule by
  its class name (crc32, the same in every process; `_stable_hashes()`) before the scene loads; equality stays identity.
  Every simulator process also runs with `PYTHONHASHSEED=0` (sets of strings).
- **The graded replays run alike** (privileged). Both graded replays run without video, the same way; the video comes
  from a third fresh-process replay, run after the verdict is written and bounded like a graded replay (PROTOCOL §4),
  that never decides anything; whether it ended on the same state is reported (`video_replay_matches`).
- **`s.status()` changes nothing.** The q_score counts the goal's satisfied predicates by evaluating them; that fills the
  object states' value caches, which OmniGibson reuses at later steps while objects have moved less than a tolerance, so
  `status()` restores every object state's cache after the evaluation. The state hash (`og.sim.dump_state`) only reads.

## Success: held for 1 s, released and at rest
The rule (`REST_*`, `RestWatch`, `Session._success_step` in the tooling, so the privileged session, the standard service and every
replay apply it at the same control step): the goal holds for `REST_STEPS` = 30 consecutive control steps (1 s of
simulated time), on each of them no **goal object** (a BDDL object the `:goal` names, as an instance or through a
quantifier's category; a tool the goal does not name may stay in the hand) is attached to a gripper by assisted grasping,
and every goal object's base link is slower than `REST_SPEED_M_S` = 0.05 m/s. The episode ends at the end of that window.
When the actions run out first (a trajectory's last row; a standard episode the agent ended), the robot holds still (the
last command, the base at 0) for up to `SETTLE_STEPS` = 150 control steps (5 s, `Session.settle()`; every replay runs it
after the last row; in standard mode, when the agent's episode is still running at its end, the sim service runs it on
the live simulator after the agent's container is stopped and a success there is the episode's, `settled_success` (the
end signal's thread stops the HTTP loop and the request thread steps the window, as a step from the signal's thread
deadlocks Isaac), so a trajectory recorded to the first
frame of the goal with the objects released still passes once they settle. `status()["goal"]` is the bare goal,
`goal_objects_held` / `goal_objects_moving` what keeps the window open; `reward.json` `goal`, `settle_steps`. The BDDL
goals themselves are the challenge's and unchanged; goals looser than their task texts (stacking_wood, chop_an_onion,
make_microwave_popcorn, ...) are a maintainer decision (they come from the official challenge).

## Simulator breakdown
The tooling checks the robot every control step and the goal objects every 30 (`BREAKDOWN_*`): a non-finite robot
state, the robot or a goal object farther than 10 km from the origin, or the robot base faster than 100 m/s end the
episode with reason "failure: simulator breakdown (...)" (`status()["breakdown"]`), a failure the verifiers record as
`sim_breakdown` = 1 and the agent's 0: the breakdowns on record were mostly the agent's own doing (a NaN base
orientation after the robot tumbled), and an infrastructure failure would be voided and run again (PROTOCOL H.5).
Whether a breakdown should be infrastructure is an open owner decision. A read that fails is no evidence: the check
stands down.

## Re-grading recorded results
`scripts/behavior/regrade.py JOBS_DIR... [--gpus 0,1] [--select candidates|all] [--dry-run]` (host side, from the
repository root: docker, the private `eai-behavior` image, an RTX GPU, `$RCB_BEHAVIOR_DATA`) runs the family's current
privileged `tests/grade.py` (two fresh-process replays, no video) on each recorded trajectory and writes old / new
verdicts as JSON lines. `goal_first_step` (`reward.json`, the first control step the bare goal held, -1 never) is the
older first-step rule, so an old success that fails now is labelled `stricter rule` when the bare goal still held in
the replay here and `inconclusive` when the replay went elsewhere (re-grade on the host class it ran on). The default
`--select candidates` re-grades the trials whose verdict can change: old successes and
failures whose replays succeeded or disagreed (standard: also a live success). Privileged re-grades are close to exact
(the deliverable is the trajectory; only the settle window after its last row is added). Standard re-grades are
conservative: the old service ended the live episode on the first step the bare goal held, where the agent could otherwise have
gone on and let go, so they only say whether the recorded rows plus the settle window reach the current rule; a
standard trajectory over 40,000 rows cannot be re-graded with the privileged grader. A re-grade that ends on a
breakdown is a 0 with `sim_breakdown` (see Simulator breakdown); `regrade.py` labels it.

### Whose failure a 0 is
How a 0 that is not the agent's is reported (`reward.json`):
- **Standard.** `final.json` is the trusted sidecar's own file (a frozen start that does not rebuild is the service's
  `instance_mismatch` give-up), so `tests/grade.py` reports `infra_error` = 1 (no verdict on
  the agent) when it is missing (`missing_log`: the service never came up, or its container was gone), unreadable
  (`grader_error` too) or not finalized (the collect hook did not finish). A reward is written in every case. The layer's
  give-ups keep their meaning: `sim_crashed_on_call` is the agent's 0, `sim_crashed` and `resume_failed` are `infra_error`.
- **Privileged.** A file the agent wrote that cannot be graded (not an npz, pickled or object arrays, no `task` or
  `actions` entry, a wrong shape, non-finite values, more than 40,000 rows) is `bad_trajectory`; a replay process that
  dies or runs out of time is `grader_error` and `infra_error` (`replay_failed`, `replay_timed_out`); `instance_ok` = 0
  (the frozen scene did not rebuild to the recorded one in the verifier, decided before the first action) sets both
  too. The tooling's `replay` CLI skips an extra npz entry it cannot read, and a failure of
  its video recorder to start or stop is only reported (`video_error`), it never decides a replay.
- **Runaway guard.** The tooling ends an episode at `MAX_STEPS` = 200,000 control steps (1.85 h of simulated time; the
  challenge's timeout termination lifted that far). It is not a step budget, but it exists, so both instructions state it
  and the standard `/spec` carries it as `max_control_steps` (reason `step_guard`).
- Tests without a simulator: `python3 -m unittest discover -s scripts/behavior/tests` (`test_grading.py`: both graders and
  the whole `finalize.sh` on synthetic records; `test_standard_service.py`: the real service and shared layer on a stub
  simulator over HTTP).

## Falls
The episode ends, as a failure, when the robot has fallen over: OmniGibson's own `Falling` termination condition
(`omnigibson/termination_conditions/falling.py`; OmniGibson's navigation tasks use it, `BehaviorTask` has only `Timeout`
and `PredicateGoal`) with its defaults, on the pose it reads (`robot.get_position_orientation()`, the R1Pro's `base_link`):
the base more than 0.03 m below the floor, or its up axis tilted more than 41.4° from vertical (z < 0.75), holding for 300
consecutive control steps (10 s of simulated time). It runs inside the tooling's `Session.step()` (`FALL_*`, `FallWatch`),
so the privileged session, the standard service and every fresh-process replay apply it at the same control step; a success
on the same step stands.
- **Standard:** `reason` "failure: the robot fell over"; `/spec` `episode` states the end conditions; `reward.json`
  `task_failure`. **Privileged:** `Session.status()["fallen"]` and `s.episode_done` (`s.reset()` starts again); the
  verifier's replays end at the same step (`reward.json` `fallen`).
- The R1Pro's base hangs from an upright world-fixed root through six virtual joints (x, y, z, rx, ry, rz; rx and ry
  undriven), so the up axis's z is also cos(rx)·cos(ry) of `base_footprint_rx_joint` / `_ry_joint`, columns the standard
  proprioception always had (checked against the `base_link` quaternion to 1e-6 on 16,973 logged rows).
- **Why the hold:** a short topple that is over within seconds (driving, bumping into furniture) never counts; the longest
  recorded lasted 4.3 s.
- **What it decides:** in OmniGibson a toppled R1Pro can sometimes be righted (agents levered it up with an arm); the
  rule is the benchmark's decision that a robot which has fallen over has failed, as in OmniGibson's navigation tasks
  and on the real robot, not a claim that recovery is impossible in the simulator.
- Measured through the task's own Session, with OmniGibson's `Falling._step` evaluated on the same state at every step
  (all in agreement): a recorded topple ended the episode exactly 300 control steps after it began; the reference rows
  never come near the threshold (at most 21.7°); the rule costs 0.06 ms of a 47-60 ms control step.

## Standard mode (eai-standard/2.2)
`joint_position` (25: base per-step targets in the robot frame, trunk, arms, grippers; base and grippers switch at the
row) and `ee_pose` (16, left first, xyzw, cuRobo IK for both end effectors per row, base still); the head camera and two
wrist cameras (link-mounted, 224×224); OmniGibson `depth_linear`; `/kinematics` on a numpy model of the articulation
(trunk + arms, cuRobo fallback; base frame unless `base_pose` is given); 121 proprio columns. docs/protocol/standard_mode.md §16.

Requests are checked before anything is executed: a null is the default, and a wrong type or an out-of-range value of
`dt`, `seconds`, `video_fps` (1-30), `cameras`, `note`, `interpolate`, `video`, `depth`, a zero `ee_pose` quaternion or
a position beyond 1000 m is a 400 and nothing runs. `dt` must be a whole number of 1/30 s control periods.

Crash recovery (docs/protocol/standard_mode.md §13): the adapter `environment/sim/server.py` journals every executed control step
(`journal.f64`), checkpoints every completed call with the full simulator state hash (`og.sim.dump_state`) and the robot's
proprio row, and resumes the same episode after compose's `restart: on-failure:6`. Resume class **`approx`**: a hash
mismatch after the journal replay is recorded (`resume_state_mismatch`) and the episode continues unless a TCP is more
than 0.05 m from its checkpoint. A replayed episode that ends before the logged rows are done (the rollouts are not
bit-exact) does not raise on the next row: the remaining rows are skipped, and
the episode ends as a success if the goal holds (the live episode's verdict), otherwise the resume is refused
(`resume_failed`, `infra_error`: a fall only the journal replay had is not the agent's). `RCB_STARTUP_TIMEOUT_S` = 1800 s: scene builds measured 130-404 s on a warm cache
(laptop trials) and 433-519 s cold on a loaded lab, plus the trial's cold-cache shader compile (~4 min); 1800 s is at
least twice every measured build. A resume replays the episode at ~14-20 steps/s (a 50k-step episode: 45-60 min of
downtime on the agent's wall clock). Artifacts: `final.json`, `episode.jsonl`, `trajectory.npz`, `journal.f64`,
`startups.jsonl`, `server.log`, the live video (and the video-only render's log when it ran).

## Tooling (file names)
| main's convention | BEHAVIOR-1K |
|---|---|
| `environment/rcb_traj.py` (privileged tooling, `Session`) | `environment/rcb_behavior.py` (`Session`: the frozen instance, thin primitives, the robot's cameras, recording, replay) |
| `tests/rcb_traj.py` | `tests/rcb_behavior.py` |
| standard sidecar | `environment/sim/server.py` (2.2 adapter), `finalize.sh`, `rcb_behavior.py`, the robot config; `rcb_limited.py`, `rcb1.py`, `run.sh` from `scripts/eai_standard/` |
| reference tooling | `solution/rcb_behavior_ref.py` (frozen; the oracle agent only) |
| `rcb_client.py`, `rcb1.py` | the same names (`scripts/eai_standard/`); the agent container and the verifier are FROM the shared digest-pinned client image (`scripts/eai_standard/client.env`), the agent's pip pins are `environment/client-requirements.txt` |

The tooling records 25-D actions (base + trunk + arms + grippers) at 30 Hz. Every copy of the tooling and of the standard
sidecar files is byte-identical across the benchmark (`check-tooling-identity.sh`).

## Declarations
- **Tooling: thin wrappers only.** Joint moves, a straight-line base drive, cuRobo IK moves, gripper commands and the
  robot's cameras. Task-level skills (grasp, place, navigate) are never added to the agent's tooling; the reference
  solutions keep theirs in `solution/rcb_behavior_ref.py`.
- **World-frame information.** Standard tasks never say where things are in the world (docs/protocol/standard_mode.md §10,
  `scripts/behavior/ci/advisory-world-frame.sh`); the convention that the floor is the plane z = 0 defines the world frame and is given.
  Privileged tasks give the privileged state through the tooling.

## Licences
BEHAVIOR-1K code (including the BDDL activity definitions): MIT; the BEHAVIOR Data Bundle: no redistribution (mounted,
never copied); Isaac Sim 5.1 and Omniverse Kit: NVIDIA proprietary (no redistribution), hence BUILD_ONLY.

## Known issues
- Privileged agents' containers mount `/behavior-src` and `/opt/tools` read-only (agents that edited OmniGibson and robot
  files in their own container saw live runs diverge from the grader's): each is a volume of
  the trial that Docker fills from the image at the first mount. The robot assets live in the dataset mount, read-only too.
  The conda environment's site-packages (Isaac Sim's extensions) stay writable; the grader uses its own image anyway.
- While the robot moves, a frame shows the scene 2 control steps before its `frame_step` (renderer latency).
- `turning_on_radio`: the radio shows no visual change when it is on, so a standard-mode agent cannot see its success.
- Supplementary goals that create objects (`real`: halves, diced pieces, cooked food, a pizza) or clean surfaces (`not
  covered`) depend on OmniGibson's transition rules and particle states. The challenge's evaluator turns the transition
  rules on (`gm.ENABLE_TRANSITION_RULES = True`) and runs PhysX on the CPU (`gm.USE_GPU_DYNAMICS = False`); every particle
  system these tasks use is a macro system (diced food, grated cheese: macro physical; dirt, dust, mud, rust, debris: macro
  visual), which needs no GPU dynamics. Whether a replay that creates objects stays bit-exact in a fresh process has not been
  measured yet (no positive example of such a task exists).

## Standard-mode service details

Resume class `approx` (OmniGibson declares rollouts nondeterministic; measured: live = fresh replay, so it normally
resumes exactly). The record dir is `RCB_DATA=/out` (`/data` is its dataset). Its service states no
`max_frames_per_call` yet. A frame's `extrinsic_cv` is the pose it was rendered with, the proprio row the state at
`frame_step`.

| | |
|---|---|
| simulator | OmniGibson 3.9.2, R1Pro |
| rows streamed at | 30 Hz control (4 substeps) |
| `joint_position` | 25: base (per-step targets, robot frame) + trunk + arms + grippers |
| `ee_pose` | 16 (left first, xyzw), cuRobo IK for both end effectors per row |
| cameras | head + two wrist cameras (224×224, moving) |
| depth | OmniGibson `depth_linear` |
| `/kinematics` | numpy model of the articulation (trunk + arms), cuRobo fallback |
| proprio columns | 121 |
| grading replays | none (graded live; a video-only render when the live video is missing) |
| resume class (docs/protocol/standard_mode.md §13.1) | `approx` |

Measured scene builds (episode `start` minus the end of Harbor's environment setup, from standard-mode trials on the laptop, RTX 4090 laptop GPU, 32 GB: a lower bound of the build):

| benchmark | measured | build | note |
|---|---|---|---|
| BEHAVIOR-1K | 6 families (12 trials) | 130–404 s (scene load); cold builds on a loaded lab host 433–519 s | `RCB_STARTUP_TIMEOUT_S` = 1800: each trial starts with a cold Kit cache (its own `*_trusted` volume), about 250 s more |
