# BEHAVIOR-1K

BEHAVIOR-1K v3.9.2 (OmniGibson 3.9.2 on Isaac Sim 5.1, the stack the 2026 BEHAVIOR Challenge pins): household tasks for
the R1Pro mobile manipulator. `simulator = "behavior"`, `robot = "r1pro"`. 100 challenge tasks (the 2026 challenge's full set), each as a privileged task
`behavior-<family>-i00-privileged` and its standard twin `behavior-<family>-i00-standard`, on the 2026 challenge's
public_test instance 301: the 11 of the first release, which have a reference solution or a positive example, and 89
supplementary tasks for harder testing (50 on 2026-10-04, 16 and 23 on 2026-10-07, below), which have neither yet.

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
  reserve `count: 1` (PROTOCOL §2.4), which Docker serves with the host's first GPU (GPU 0).
- About 13-16 GB of RAM per Isaac process: one Isaac simulator at a time on a 32 GB host. torch / OpenMP pools are capped
  at 8 threads in every compose service that runs the simulator (uncapped they span every core of a large host and run up
  to 15× slower).

## Tasks and generator
- `scripts/behavior/mk_tasks.py` generates every task from the template twins `tasks/behavior-picking-up-trash-i00-privileged`
  and `-standard` (maintained by hand), `scripts/behavior/families.json` (the texts of each family: goal, success conditions,
  difficulty, the standard goal in words; the oracle level and its evidence: the cited positive, or the challenge's
  official human demonstrations, `"demo"`; `"added"`, the date of the pull request of a family added after the first 50, and
  its own `"review_pr"` where a later pull request reviews it; `"include"`), the BDDL problems
  `scripts/behavior/bddl/` (BEHAVIOR-1K's `bddl` package, MIT: `/behavior-src/bddl3/bddl/activity_definitions/<task>/problem0.bddl`
  in the image), the frozen instances `scripts/behavior/instances/` and the reference solutions
  `scripts/behavior/solutions/`, plus the eai-standard/2.2 layer from `scripts/eai_standard/`. A rerun reproduces the
  committed tasks; `mk_tasks.py --check` regenerates into a temporary tree and diffs. It writes every README in the
  protocol's layout and ends each task with `scripts/task_conventions.py`'s `normalize()`, like every generator.
  `scripts/behavior/goal.py` words each BDDL predicate a goal uses, with OmniGibson's thresholds. Agent results are not
  in the repository (PROTOCOL D3): the positives are cited by trial id, results-site log and Hugging Face replay.
- The predicate is the task's official BDDL goal (OmniGibson object states), checked at every control step; the episode
  ends the moment it holds, and as a failure when the robot has fallen over (§ Falls). The challenge's timeout is lifted to
  a runaway guard (time is the budget, not steps).
- Frozen instance: the full simulator state after the challenge's own instance load (`Evaluator.load_task_instance`) and
  its hash, in `environment/`, `tests/` and the standard sidecar. Another host may rebuild it within the pose tolerance but
  not bit-exactly (`instance_exact = 0`, `instance_ok = 1`); grading needs `instance_ok`.

| family | oracle | evidence (PROTOCOL §2.7) |
|---|---|---|
| picking_up_trash, putting_shoes_on_rack | `partial` | human-written reference solutions on the frozen task-level primitives `solution/rcb_behavior_ref.py`; the standard oracle streams the privileged oracle's joint targets through the client. They scored 1 on earlier versions (`oracle_evidence` cites the runs; picking_up_trash privileged 1 of 3), and the standard twins' service, collect hook, grader and oracle client changed since (crash recovery): not re-run on this version, hence not `full` |
| clean_up_broken_glass, collecting_aluminum_cans, composting_waste, dispose_of_glass, hiding_Easter_eggs, installing_a_scanner, stacking_wood, tidying_bedroom, turning_on_radio | `none` | a privileged model trial graded 1 by the separate verifier on a pre-v1.0 version (trial id, agent log and replay in `oracle_evidence` and the README); human review per family |
| the 89 supplementary families (below) | `none` | no positive example yet: the 2026 challenge's official human teleoperation demonstrations of the activity with the R1Pro in the same scene model (the video, its duration, the number of episodes and their mean duration in `oracle_evidence` and the README); human review per family; results reported separately until a positive scores 1 (PROTOCOL §7, open item 4) |

The labels follow one rule: `full` only when a recorded oracle run scored 1 on a byte-identical grader, frozen instance and
oracle code, with every tooling change since shown to be off the oracle and replay path. This version was validated
statically (CI, the generator's `--check`), not re-run.

**Loose official goals** (reported, the official judgement is kept): `stacking_wood` only needs every log to touch
another log (no stack; its positive pushed the logs together with the robot body); `hiding_Easter_eggs` only needs the
eggs on the lawn next to one tree and out of the basket (nothing is hidden); `laying_tile_floors` only needs the tiles on
the floor, each `nextto` another; `loading_the_car` lists `(not (open ?car.n.01_1))` outside the goal's `(and ...)`, and
BDDL reads only the first expression of `:goal`, so the car may stay open; `sorting_vegetables` needs one bowl per
vegetable group, not three different bowls; `freeze_fruit` does not need the fruit frozen. The instructions say so.

## Supplementary tasks (2026-10-04)
50 more challenge tasks, added for supplementary testing on the user's selection: long official demonstrations (the
challenge's teleoperators needed 274-869 s on average, a median of about 450 s), a spread of skills, and none that the
`codex-gpt6_luna-xhigh` sweep (pre-v1.0 versions, 2026-09-25..29) solved in privileged mode: 22 of them were in that sweep
(no success in either mode), 28 never ran. Skills, by the task-list site's labels: articulated objects 25 (refrigerators,
cabinets, an oven, a car, a toolbox, a laptop), tool use 9 (knives, an axe, a broom, a scrub brush, steel wool, a lighter),
heat 6 (cooking, baking, freezing, thawing, fire), cutting and dicing 5, surface cleaning 4 (rust, mud, dirt, dust), filling
containers with particles 2, operating devices 6 (an oven, a stove, a microwave, a washing machine, a lighter), two-handed
carrying of large objects 3, outdoor scenes 7, several rooms 13. Their predicates go beyond the first release's: `real` (objects that the simulator's
transition rules create during the episode: halves, diced pieces, cooked food, a pizza), `filled` and `contains`
(particles in a container); `goal.py` words them. No reference solution was written: `oracle = "none"`, with the official
demonstrations as the solvability evidence, and the families are reviewed per family like the others (PROTOCOL §2.7).
22 of the frozen instances are the ones the sweep ran on (unchanged), 28 were frozen on 2026-10-04 with the same tooling
and `Evaluator.load_task_instance` recipe. Checked on 2026-10-04/05 on ws (RTX 4090): every new instance was frozen in a
fresh container and its goal is false at the start; fresh-process reloads of four instances (chopping_wood, polishing_shoes,
tidying_bathroom: the exact state hash; setting_the_table, frozen on another host: every object pose within tolerance,
`instance_ok`) and Harbor `nop` runs in both modes on three families (setting_the_table, canning_food,
assembling_gift_baskets: 0, no infrastructure error) passed; CI and the generator's `--check` pass.

Families: assembling_gift_baskets, boxing_books_up_for_storage, bringing_in_wood, bringing_paper_to_recycling, can_meat,
canning_food, carrying_in_groceries, carrying_out_garden_furniture, chopping_wood, clean_a_patio, clean_up_your_desk,
clean_your_rusty_garden_tools, cleaning_up_branches_and_twigs, cleaning_up_plates_and_food, clearing_food_from_table_into_fridge,
collecting_childrens_toys, cook_brussels_sprouts, cook_cabbage, dispose_of_batteries, freeze_fruit, freeze_pies,
getting_organized_for_work, laying_tile_floors, loading_the_car, make_pizza, moving_boxes_to_storage, organizing_school_stuff,
outfit_a_basic_toolbox, picking_up_toys, polishing_shoes, put_together_a_basic_pruning_kit, putting_away_Halloween_decorations,
putting_away_toys, putting_dirty_dishes_in_sink, putting_dishes_away_after_cleaning, putting_up_Christmas_decorations_inside,
rearrange_your_room, setting_mousetraps, setting_the_fire, setting_the_table, setup_a_bar_for_a_cocktail_party,
slicing_vegetables, sorting_household_items, sorting_vegetables, storing_food, thawing_frozen_food, tidying_bathroom,
tidying_living_room, unloading_the_car, wash_dog_toys.

### Second batch (2026-10-07)
16 more challenge tasks, added at the user's request: boxing_food_after_dinner, bringing_water, cook_a_brisket,
cook_broccolini, hanging_pictures, make_gift_bags_for_baby_showers, make_rose_centerpieces, organizing_art_supplies,
packing_meal_for_delivery, preparing_lunch_box, rearranging_kitchen_furniture, set_up_a_coffee_station_in_your_kitchen,
sorting_books_on_shelf, store_honey, store_produce, vacuuming_floors. The review of 2026-10-01 had kept them out (no
oracle and no positive example); they join the 50 on the same terms: the frozen public_test instance 301 that
`scripts/behavior/instances/` already held (the same robot config and OmniGibson 3.9.2 as the others), `oracle = "none"`, the official
demonstrations as the solvability evidence (`demo`, from the challenge's task list like the 50's), and results reported
separately until a positive scores 1 (PROTOCOL §7, open item 4). Their teleoperators needed 80-322 s on average (a median
of about 235 s): shorter tasks than the 50. Their predicates are the 61's (`inside`, `ontop`, `open`, `nextto`, `cooked`,
`covered`) plus `attached` (hanging_pictures, the poster on a wall nail), which `goal.py` words. Their `families.json`
entries carry `added` (2026-10-07), so that `oracle_evidence` and the README name the pull request of the human review
(`REVIEW_PR` in `mk_tasks.py`) instead of "per family".
Checked on 2026-10-07 on ws (one RTX 4090 shared with other users' jobs, one job at a time): Harbor `nop` in both modes on all
16 families scored 0 with no infrastructure error (privileged: no trajectory, `missing_trajectory`, about 30 s; standard: one
simulator start, the episode finalized without a step, `live_success` and `replay_success` 0, `deterministic` 1, the live state
hash equal to both fresh-process replays', 515-1355 s per run). The frozen instance rebuilt bit-exactly in 5 families
(bringing_water, make_gift_bags_for_baby_showers, preparing_lunch_box, store_honey, store_produce) and with every object pose
within tolerance in the other 11 (`instance_ok`, not `instance_exact`). A nop takes no step and OmniGibson judges the goal only
inside `step()`, so it does not show that a goal is false at the start; each family's BDDL `:init` does (the review table of the
pull request). The generator's `--check`, `task_conventions.py --check` and the per-task CI checks pass on the 32 directories.

### Third batch (2026-10-07)
23 more challenge tasks, the ones `families.json` did not know at all: clean_boxing_gloves, wash_a_baseball_cap,
attach_a_camera_to_a_tripod, clean_a_trumpet, spraying_for_bugs, spraying_fruit_trees, make_microwave_popcorn, chop_an_onion,
cook_hot_dogs, cook_bacon, sorting_bottles_cans_and_paper, re_shelving_library_books, sweeping_garage, scrubbing_bathroom_floor,
halve_an_egg, installing_smoke_detectors, turning_out_all_lights_before_sleep, cook_a_frozen_pie, installing_a_modem,
make_cabinet_doors, store_batteries, installing_a_fax_machine, clean_a_keyboard. With them the benchmark has all 100 tasks of
the 2026 challenge, added at the user's request on the same terms as the 66: `oracle = "none"`, the official demonstrations as
the solvability evidence (`demo`, same recipe; the teleoperators needed 80-342 s on average, a median of about 213 s), results
reported separately until a positive scores 1 (PROTOCOL §7, open item 4). Their `families.json` entries carry `added` and
`review_pr: third_batch`, which `THIRD_BATCH_PR` in `mk_tasks.py` resolves ("TBD" until the pull request that reviews them
exists), so their `oracle_evidence` and READMEs name that pull request instead of the second batch's. Texts are written from the
BDDL goals; the BDDL problems are copied from the image. Their predicates are the 77's; `office_cubicles_right`
(installing_a_fax_machine, clean_a_keyboard) is a scene no earlier task used.
- **Registry.** The instances were frozen with `make-instance`, so the three tooling copies of `rcb_behavior.py` (the template
  twin's privileged `environment/`, and with it every task's `tests/` and standard `environment/sim/`) gained the 23 `TASKS`
  entries and nothing else: the 77 existing tasks regenerate identically apart from those entries (231 copies, each the
  previous one plus the 23 added entries; no `solution/` file touched), so the oracle levels of the template twins stand.
- **Freeze and check** (2026-10-07, RTX 4090 hosts shared with other users' jobs, one simulator at a time): each instance was
  frozen with the challenge's own `Evaluator.load_task_instance` recipe (public_test instance 301), then reloaded in a fresh
  process of the same host: the state hash matched exactly, every object pose matched, and the BDDL goal, evaluated at the start
  with the task's own goal checker, was false in all 23. (Not `task.success`: OmniGibson sets it False on reset and judges the goal
  only inside `step()`, so it would say "false" for any goal.) 20 instances were frozen on ws with the official
  `eai-behavior:0.1.1`; 3 (attach_a_camera_to_a_tripod, spraying_for_bugs, wash_a_baseball_cap) on a second RTX 4090 host (ws3)
  with its local image, a build of this repository's `images/behavior/Dockerfile` (ffmpeg pinned to the 2026-09-20 archive
  snapshot): the same simulator layers, only the ffmpeg apt layer differs, and ffmpeg is not used by freezing, reloading or `nop`.
- **Loose official goals** (reported, the official judgement is kept): `spraying_for_bugs` and `spraying_fruit_trees` need the plants
  and trunks `covered`, which is true as soon as particles of the substance are on them (not "fully covered", as the challenge's
  instruction says); `cook_hot_dogs`, `cook_bacon` and `cook_a_frozen_pie` need only `cooked`, from any heat source (not
  necessarily the microwave, the pan or the oven); the cleaning and washing tasks (clean_boxing_gloves, wash_a_baseball_cap,
  clean_a_trumpet, clean_a_keyboard, sweeping_garage, scrubbing_bathroom_floor) need only `not covered`, however the substance
  leaves. The instructions say so.
- **nop** (2026-10-07, 18:19-20:58 CDT, one job at a time per host, the default configuration): Harbor `nop` in both modes on all 23
  families scored 0, with no infrastructure error and none scoring 1. Privileged: no trajectory (`missing_trajectory`), about 30 s,
  no simulator. Standard: one simulator start, the episode finalized without a step, `live_success` and `replay_success` 0,
  `deterministic` 1, the live state hash equal to both fresh-process replays', 382-1253 s per run. The reload by the standard nops
  gave the frozen state hash in all 23 families, across the hosts too (3 instances frozen on ws3 reloaded exactly on ws, and the 7
  nops run on ws3 reloaded instances frozen on ws). 39 runs were on ws with the official image; 7 standard runs (cook_bacon,
  re_shelving_library_books, scrubbing_bathroom_floor, installing_smoke_detectors, make_cabinet_doors, store_batteries,
  turning_out_all_lights_before_sleep) were on ws3 with the pinned build above, through staged copies of the task directories
  whose `docker-compose.yaml` names that image by a private tag (the committed directories are unchanged). A nop takes no step and
  OmniGibson judges the goal only inside `step()`, so it does not show that a goal is false at the start; the freeze check does
  (the goal was false at the start in all 23, measured with the task's own goal checker). The generator's `--check`,
  `task_conventions.py --check` and the per-task CI checks pass on the 46 directories.

## Time budget (D8)
14400 s (the protocol maximum) for every task of both modes, the same in the whole benchmark:
- every Python process pays an Isaac launch and scene load: about 2-3 minutes with a warm Kit cache, and the first launch
  of a trial adds about 4 minutes to compile shaders into the trial's own cache (below);
- the simulator runs 7-18 control steps/s depending on the host (30 Hz control), and these tasks take thousands of
  steps: the 9 positives are 1,374-7,200 control steps long, the challenge's teleoperators averaged 531 s (15,939 steps)
  for stacking_wood alone;
- measured: the 9 positives used 2,251-12,791 s of agent time (median 7,917 s); 8 of the 9 would not have finished in
  the 3600 s default.

### Verifier time (2026-10-08)
Time limits only; the pass rules are unchanged. Measured on an idle 8-vCPU L40S host (job #3137, a privileged can_meat
trajectory of 10,475 control steps): the Isaac start took 626 s, and the replay had not finished when the old flat 3600 s
per replay ran out, i.e. it ran slower than 3.5 control steps/s (AWS L40S/L4 and Slurm L40S hosts with 8 vCPU are the eval hosts).
- **Privileged.** `tests/grade.py` gives each of the two fresh-process replays `min(4 h, max(3600 s, 1200 s + steps / 2))`:
  20 min for the Isaac start plus a worst case of 2 control steps/s, never less than the old 3600 s, at most 4 h (enough for
  26,400 steps at 2 steps/s, ~46,000 at 3.5). A replay over its limit is a grader error (`grader_error` = 1,
  `replay_timed_out` = 1), as before. `[verifier] timeout_sec` = 30600 s: two capped replays plus 30 min.
- **Standard.** The collect hook (`environment/sim/finalize.sh`) replays with the same tooling CLI;
  its `[[verifier.collect]] timeout_sec` = 37800 s (was 6 h): the episode end (up to 2 h through a resume) plus two 4 h
  replays plus 30 min. Since 2026-10-10 the hook stops a replay itself 10 minutes before that deadline (`BUDGET_S` in
  `finalize.sh` is the same 37800 s) and records it, instead of being killed with the replay (below).

## Kit cache: one per trial
Isaac keeps shaders and generated Python in its Kit cache (`/cache`). Every compose file names its cache volume without a
fixed `name:` (`rcb_behavior_cache` for the agent, `rcb_behavior_cache_trusted` for the verifier and the standard
sidecar): compose prefixes it with the trial's project name, side-by-side trials never share it, and Harbor's teardown
(`compose down --volumes`) deletes it. Measured on ws: a scene load takes 359 s on a cold cache and 110 s on a warm one,
so each container pays about 4 minutes once (the agent's first `Session`, the sidecar's start, the verifier's first
replay; the second replay reuses the cache). That is under 2 % of the agent budget, and it removes a global volume that
agents of different trials could write and that a concurrent trial's teardown could delete. A read-only shared cache
was the alternative: Kit writes to its cache at run time, so it would need a host-prepared cache plus a writable copy per
container, outside Harbor's lifecycle. A cache can reach ~10 GB (one probe volume: 9.8 GB); it lives as long as the trial.

## Host notes (host-local, never committed)
- **GPU pin.** `count: 1` always gives GPU 0. A host whose BEHAVIOR GPU is another one (lab) pins it at run time with a
  host-local compose override (`device_ids` on `main` / `sim`, like lab's verifier-subnet patch), applied to its own copy
  of the tasks and written down in that host's notes, never committed: a committed `device_ids` is a MUST NOT
  (PROTOCOL §2.4).
- **Docker address pools.** A host with exhausted pools (lab) gives each trial explicit subnets (its agent environment
  through an extra compose file, its separate verifier through a patch of its copy of `tests/docker-compose.yaml`). The
  standard verifier needs no network (`no-network`).
- **Privileged verifier network.** The privileged verifier keeps Harbor's default network instead of `no-network` (a
  SHOULD, PROTOCOL §2.6): it starts Isaac Sim, and an Isaac / Omniverse Kit start in a container without any network
  interface has not been tested (with only the model APIs reachable it starts and loads the scene as before: Network,
  below). It downloads nothing: the dataset is mounted and the image is complete.

## Network
The agent reaches the model APIs and, since 2026-10-11, the package registries (PyPI, apt archives), nothing else: `[agent] network_mode = "allowlist"` with the hosts of
`scripts/set_agent_egress.py`, which `mk_tasks.py` (`agent_egress`) writes into every task (owner decision 2026-10-10,
board 0072). Until then the tasks had Harbor's default, public egress: they were added on 2026-09-20 without a network
setting, and the repository-wide default of 2026-09-24 (kept on 2026-10-02) left them so. There was no technical reason:
nothing in a BEHAVIOR container needs the network at run time. The image holds Isaac Sim, OmniGibson, cuRobo and every
Python package, the scenes and robot assets come from the mounted dataset, and the EULA is accepted by an environment
variable. What the open egress did allow was a download of the 2026 challenge's public material for the same activities
(its teleoperated demonstrations, which a task's name locates, and its baselines) and of packages.

| Service | Before | Since 2026-10-10 |
|---|---|---|
| privileged `main` (agent and its Isaac processes) | public | public from container start until the agent starts (the harness is installed then), the allowlist (the model APIs and the package registries) while the agent runs |
| standard `main` (agent, client only) | public | the same |
| standard `sim` (the simulator service) | public | the same as `main`: Harbor's egress control puts every compose service without a network setting of its own in one namespace, so the service's Isaac start (it begins at container start and takes about 10 minutes) and a restart after a crash run with the allowlist only; public again while the collect hook replays the episode |
| `rcb_monitor` | none | none |
| privileged verifier | public (Harbor's default) | unchanged |
| standard verifier | none (`no-network`) | unchanged |

Checked on real simulators (2026-10-11, L40S hosts, the oracle of `picking-up-trash` with a probe run from inside the
agent's container first): GitHub, PyPI (`pip download`), Hugging Face and NVIDIA's Omniverse content bucket were
unreachable and the OpenAI, Anthropic and OpenRouter APIs answered. The results equal the
open-egress runs of the same oracles on the same host class (board 0067, R2): privileged, the `partial` oracle's reward 0
with `q_score` 0.667, 4,390 steps, the same initial and final state hashes, `deterministic` 1 and no error flag;
standard, reward 1 with live = replay = 1, `deterministic` 1, 5,114 steps and one simulator start. Isaac was not slower
to start (evaluator ready after 674 s in the agent's container and 631 s in the service, against 757 s and 652 s), and
its log has no failed download: the scene loads from the mounted dataset alone.

## Grading and determinism
- Privileged: the verifier replays `trajectory.npz` from the frozen instance in **two fresh processes** (an in-process
  reset is approximate; the first replay in a fresh process reproduces a live run bit for bit) and needs the goal after
  both, equal final-state hashes and `instance_ok`.
- Standard: the service dumps the episode (artifacts under `/out`, since `/data` is the dataset) and exits on the collect
  hook's signal; the hook replays it in two fresh processes (`environment/sim/finalize.sh`); `success = live ∧ replay ∧
  deterministic`, `live_matches_replay` reported separately. OmniGibson declares rollouts nondeterministic; measured so
  far, a live run and its fresh replay agree.

### Whose failure a 0 is (2026-10-10, review of board 0067)
The pass rules are unchanged; what changed is how a 0 that is not the agent's is reported (`reward.json`).
- **Standard.** `final.json` is the trusted sidecar's own file, so `tests/grade.py` reports `infra_error` = 1 (no verdict on
  the agent) when it is missing (`missing_log`: the service never came up, or its container was gone), unreadable
  (`grader_error` too), not finalized (the collect hook did not finish; the file is the service's own copy without the
  replays), or says a fresh-process replay did not run to its result (`replay_error`: the process died, printed no result
  or ran out of time; `finalize.sh` records each replay's exit code). A reward is written in every case. The layer's
  give-ups keep their meaning: `sim_crashed_on_call` is the agent's 0, `sim_crashed` and `resume_failed` are `infra_error`.
- **Privileged.** A file the agent wrote that cannot be graded (not an npz, pickled or object arrays, no `task` or
  `actions` entry, a wrong shape, non-finite values, more than 200,000 rows) is `bad_trajectory` (it was `grader_error`
  for the unreadable ones); a replay process that dies or runs out of time stays `grader_error` and now also sets
  `infra_error` (`replay_failed`, `replay_timed_out`); `instance_ok` = 0 (the frozen scene did not rebuild to the recorded
  one in the verifier, decided before the first action) sets both too (it was a plain 0). The tooling's `replay` CLI skips an extra npz entry it cannot read, and a failure of
  its video recorder to start or stop is only reported (`video_error`), it never decides a replay.
- **Runaway guard.** The tooling ends an episode at `MAX_STEPS` = 200,000 control steps (1.85 h of simulated time; the
  challenge's timeout termination lifted that far). It is not a step budget, but it exists, so both instructions state it
  and the standard `/spec` carries it as `max_control_steps` (reason `step_guard`).
- Tests without a simulator: `python3 -m unittest discover -s scripts/behavior/tests` (`test_grading.py`: both graders and
  the whole `finalize.sh` on synthetic records; `test_standard_service.py`: the real service and shared layer on a stub
  simulator over HTTP).

## Falls (2026-10-09, owner decision)
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
- **What it decides:** in OmniGibson a toppled R1Pro can sometimes be righted. In the eight recorded standard-mode runs
  with the robot's proprioception (saved or printed by the agent; rcb-limited/2.0 and 2.2, 2026-09-25..30) five toppled
  past 41°, 14 times: 12 topples ended upright again (up to 145°): eight within 4.3 s of simulated time, four after the
  agent levered the robot up with an arm against the floor over 32-114 s; two lasted until the 4 h limit. None of the eight
  runs succeeded; with the rule three of them would have ended 2.3-3.4 h early, two of them after a topple the agent later
  recovered from. The rule is the benchmark's decision that a robot which has fallen over has failed, as in OmniGibson's
  navigation tasks and on the real robot, not a claim that recovery is impossible in the simulator. The scene, the frozen
  instances and the BDDL goals are unchanged, so the tasks keep their names (owner decision, as for HumanoidBench's and
  MyoSuite's reset budgets); results recorded before this change are reported separately.
- Measured on ws (RTX 4090, 2026-10-09) through the task's own Session, with OmniGibson's `Falling._step` evaluated on the
  same state at every step (12,036 control steps, all in agreement): a standard agent's recorded rows that toppled the robot
  ended the episode exactly 300 control steps after the topple began (on its side, 94.7°); the reference rows never came
  near the threshold (putting_shoes_on_rack at most 21.7°, p99.9 17.3°; picking_up_trash at most 7.5°); the rule costs
  0.06 ms of a 47-60 ms control step.

## Standard mode (eai-standard/2.2)
`joint_position` (25: base per-step targets in the robot frame, trunk, arms, grippers; base and grippers switch at the
row) and `ee_pose` (16, left first, xyzw, cuRobo IK for both end effectors per row, base still); the head camera and two
wrist cameras (link-mounted, 224×224); OmniGibson `depth_linear`; `/kinematics` on a numpy model of the articulation
(trunk + arms, cuRobo fallback; base frame unless `base_pose` is given); 121 proprio columns. STANDARD_MODE.md §16.

Requests are checked before anything is executed (PROTOCOL §4.6; 2026-10-10): a null is the default, and a wrong type or
an out-of-range value of `dt`, `seconds`, `video_fps` (1-30), `cameras`, `note`, `interpolate`, `video`, `depth`, a zero
`ee_pose` quaternion or a position beyond 1000 m is a 400 and nothing runs; before, several of these raised inside the
service and ended the one episode as a simulator error (`video_fps` = 0 and a non-string `note` only after the chunk had
run). `dt` must be a whole number of 1/30 s control periods: it used to be rounded (0.25 s ran as 8 steps, 0.267 s).

Crash recovery (STANDARD_MODE.md §13): the adapter `environment/sim/server.py` journals every executed control step
(`journal.f64`), checkpoints every completed call with the full simulator state hash (`og.sim.dump_state`) and the robot's
proprio row, and resumes the same episode after compose's `restart: on-failure:6`. Resume class **`approx`**: a hash
mismatch after the journal replay is recorded (`resume_state_mismatch`) and the episode continues unless a TCP is more
than 0.05 m from its checkpoint. A replayed episode that ends before the logged rows are done (the rollouts are not
bit-exact) no longer raises on the next row, which crashed every restart the same way: the remaining rows are skipped, and
the episode ends as a success if the goal holds (the fresh replays still decide), otherwise the resume is refused
(`resume_failed`, `infra_error`: a fall only the replay had is not the agent's). `RCB_STARTUP_TIMEOUT_S` = 1800 s: scene builds measured 130-404 s on a warm cache
(laptop trials) and 433-519 s cold on a loaded lab, plus the trial's cold-cache shader compile (~4 min); 1800 s is at
least twice every measured build. A resume replays the episode at ~14-20 steps/s (a 50k-step episode: 45-60 min of
downtime on the agent's wall clock). Artifacts: `final.json`, `episode.jsonl`, `trajectory.npz`, `journal.f64`,
`startups.jsonl`, `server.log`, the replays' logs and video.

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
- **World-frame information (D7).** Standard tasks never say where things are in the world (STANDARD_MODE.md §10,
  `check-standard-texts.sh`); the convention that the floor is the plane z = 0 defines the world frame and is given.
  Privileged tasks give the privileged state through the tooling.

## Licences
BEHAVIOR-1K code (including the BDDL activity definitions): MIT; the BEHAVIOR Data Bundle: no redistribution (mounted,
never copied); Isaac Sim 5.1 and Omniverse Kit: NVIDIA proprietary (no redistribution), hence BUILD_ONLY.

## Known issues
- While the robot moves, a frame shows the scene 2 control steps before its `frame_step` (renderer latency).
- The per-call state hash (`og.sim.dump_state`, read-only) is new with crash recovery: the validation re-checks that
  `live_matches_replay` stays 1 on the standard oracles.
- `turning_on_radio`: the radio shows no visual change when it is on, so a standard-mode agent cannot see its success.
- Supplementary goals that create objects (`real`: halves, diced pieces, cooked food, a pizza) or clean surfaces (`not
  covered`) depend on OmniGibson's transition rules and particle states. The challenge's evaluator turns the transition
  rules on (`gm.ENABLE_TRANSITION_RULES = True`) and runs PhysX on the CPU (`gm.USE_GPU_DYNAMICS = False`); every particle
  system these tasks use is a macro system (diced food, grated cheese: macro physical; dirt, dust, mud, rust, debris: macro
  visual), which needs no GPU dynamics. Whether a replay that creates objects stays bit-exact in a fresh process has not been
  measured yet (no positive example of such a task exists).
