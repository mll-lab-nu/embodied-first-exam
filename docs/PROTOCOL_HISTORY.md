# Protocol history

The record of how [`PROTOCOL.md`](PROTOCOL.md) came to say what it says: version notes, owner decisions with their
dates and reasons, and the migrations that changed tasks in place. Moved out of PROTOCOL on 2026-10-14 (owner: "the
protocol should be as lean as possible"), unchanged in substance. Nothing here is a rule: the protocol is the current
text, and a benchmark's own choices are in `docs/benchmarks/<bench>.md` and its tasks. Where a section below names a
PROTOCOL section, it is the number the section had then, which is still its number.

## Versions

**v2.0** (2026-10-14, owner, boards 0124 / 0121). The judge's review of v1.2-rc (board 0124) found the text already
recommending, but CI still blocking every convention and the trust-boundary rules mixed in with them; a task could
"adapt a check through a declared value" even for verifier isolation. The owner's answers (Q1–Q11 as recommended):
- Eight invariants (PROTOCOL Appendix H) bind; no task value overrides them; only the required CI job `invariants`
  blocks a merge, and it fails on any failure, error or incomplete run. Every other check is advisory (exit 3,
  annotations, the "Advisories" section of the pull request's overview).
- The old MUST no longer blocks: v1's rules are conventions, reported as warnings.
- d5 changed (owner, 10-14): v1's "crash recovery resumes the same episode, never a reset, a simulator crash never the
  agent's 0" is replaced by H.5, at most one full retry after an infrastructure failure (the runner's rule). The shared
  layers' in-trial resume stays as their implementation (no task changed).
- Open network (d6): first proposed as an owner-approved exception, then (owner, 10-14) the task author's own decision,
  declared `[metadata] network = "open"`; the three prefix lists (`OPEN_EGRESS` in `check-verifier-isolation.sh` and
  `set_agent_egress.py`, `EXTERNAL_OPEN` in `task_conventions.py`) were removed. RoboOlympics' 113 generated tasks
  declare it (new digests, same instructions).
- The official-run configuration (d7) and the seed policy (d9) moved to RUNNING.md, enforced by the runner and the
  scheduler (batch_eval_live `run_policy.py`); nop / oracle (d10) became a recommendation, and results rank unvalidated
  tasks apart. Results record each trial's effective configuration and are ranked only within comparable ones.
  Changed on 2026-10-16 (owner, board 0124: "no need for this"): validated and unvalidated tasks are ranked together;
  `validated` stays in each result's configuration as a marker and a filter, and was never part of `config_key`.
- Per-benchmark lists removed from shared CI: `scripts/task_dynamics.toml` and `check-dynamics.py` (each task declares
  `[metadata] dynamics`), `NO_TWIN` (the README's Twin row is the declaration), the eight benchmarks of
  `check-standard-texts.sh` and the RoboPaint / ManiGuard leak and tooling checks (now each benchmark's own
  `scripts/<bench>/ci/{invariant,advisory}-*` hooks).
- PROTOCOL.md went from 793 to about 200 lines; v1's runner material is below ("v1.2-rc text not carried into v2.0").
- Added on 2026-10-16 (#265, the benchmark owners' easy-set selections; board 0146): §4's easy-set row and
  `docs/easy_set.toml`, task bases kept and run but reported apart from the main table (`set` = `easy`, a marker like
  `validated`, never part of `config_key`). A central list rather than a task field or a `-easy` directory name:
  membership is a judgment about how results are reported, not a property of the task, and it changes (after a grader
  fix, after more screening runs) while the task does not. A field would mint a new version of 168 task directories
  (their DIGEST, H.8) and a rename new tasks, and either would detach the results already recorded against them
  (`write_task_results.py`'s `digest_match` turns a default-seed trial of another digest into "legacy"; the pool keys
  results by directory name); the list changes no task.
- Added on 2026-10-16 (owner, board 0136: "every run must end with a video, except a privileged trial that submitted no trajectory"): §4's video row says every graded trial leaves a playable video and the replayable trajectory it was graded on, the one exception, and that the video's time bound covers the longest episode; `ci_checks/check-video.py` (advisory: a video is evidence for people, never the verdict, and a static scan cannot tell whether a render finishes in time) and the runner's `no_video` flag with an after-the-fact render from the trajectory (RUNNING.md "Recordings"). Found by the survey of 7977 graded trials: 114 without a video for reasons other than the exception (DexHand privileged rendered none; render time bounds shorter than long episodes; a RoboOlympics sport without a spectator camera).

**Version: v1.2-rc** (2026-10-10). Changes in this version: the resource monitor sidecar, the docker caps and the
verifier's limits step are in every task (§2.10; #131, with the review fixes of the same day: an out-of-memory kill is
the agent's only at its container's own cap, a benchmark-owned service killed for memory is never the agent's 0, a CPU
cap above the host's CPU count is clamped by the runner); enforcement is off by default, and v1.2 becomes final when
the calibration batch has confirmed the limits. Also on 2026-10-10 and 2026-10-11 (owner decisions, board 0072): every task's
agent egress is the model APIs and the package registries, every instruction states the same honour rule about looking
solutions up (§2.11), and the usage gateway forwards model-API calls only (D11, §5). On 2026-10-11 (owner): §4.8's exception for
physics that does not replay bit for bit (such a task is standard only and graded by the live episode; RoboDojo's six). Also on 2026-10-11 (owner, board 0080): the agent's time cutoffs live in one table (until 2026-10-14: since then each task sets its own in `task.toml`, as in Terminal-Bench; owner, board 0120), and every instruction ends with its cutoff and the request not to cheat in one format (§2.12; 2026-10-12: at the end of the instruction, and the table takes exceptions per family and per task). On 2026-10-14 (owner, boards 0106 / 0112): scene dynamics (§2.15), and every standard-realtime task states its slowdown S and allows resets, 10 by default (§4b). On 2026-10-12 (owner): §3's and §4.8's exception for grading by one replay instead of two (RoboDojo). On 2026-10-14 (owner, board 0107 E6): a benchmark ships any subset of the three modes, a general rule that replaces the per-benchmark exceptions for a missing twin (§2.15; where privileged and standard both exist, their cutoffs stay equal), and new modes may be added by pull request, through one registry of modes (§2.16). On 2026-10-14 (owner, board 0107 E7): §4c, tasks a benchmark exports with its own service and grader (RoboOlympics' matches and skill tasks). Earlier versions, whose rules are all part of this text: v1.0
(2026-09-30: the two modes and their names), v1.1 (2026-10-08: the standard-realtime mode, §4b), v1.1.4 (compute
resources, §2.9), v1.1.5 (resource limits, §2.10).

> **Names.** v1.0 renamed the two modes (unlimited → **privileged**, limited → **standard**) and the standard-mode
> protocol (`rcb-limited/2.x` → **`eai-standard/2.x`**); task directories end in `-privileged` or `-standard`. Base images
> moved to `ghcr.io/mll-lab-nu/eai-<name>` on 2026-10-02 (§7). v1.1 added a third mode, **standard-realtime** (`-standard-realtime`): standard
> mode's robot as a service, on a clock that does not stop.

## Design decisions as recorded until 2026-10-14 (§0.2)

| # | Topic | Decision |
|---|---|---|
| D1 | Standard-mode protocol | Only `eai-standard/2.x`. Additive extensions are accepted through a protocol-change PR (2.2 is accepted once its services implement crash recovery). Reset is only an optional capability (`budget.reset = N`, default 0; results with N > 0 are reported separately). Documented per-benchmark exceptions (§4.5): HumanoidBench standard defaults to N = 50 (owner, 2026-10-07), MyoSuite standard to N = 10 (owner, 2026-10-09); BiGym2 and KinDER standard to N = 10 (owner, 2026-10-11); DexToolBench standard to N = 20 (owner, 2026-10-13); MuJoCo Playground's quadruped standard tasks to N = 10 (owner, 2026-10-14). The standard-realtime mode's `eai-standard/2.3` (§4b) is 2.2 plus the realtime capability. `eai-standard/2.4` (issue #89) is 2.3 plus the operations capability; standard tasks may use it. No step caps. The one other kind: tasks a benchmark exports with its own service, grader inside, on its own named protocol (§4c; owner, 2026-10-14: RoboOlympics), 2026-10-13); DexHand standard to N = 20 (owner, 2026-10-14); MuJoCo Playground's quadruped standard tasks to N = 10 (owner, 2026-10-14). The standard-realtime mode's `eai-standard/2.3` (§4b) is 2.2 plus the realtime capability. `eai-standard/2.4` (issue #89) is 2.3 plus the operations capability; standard tasks may use it. No step caps. |
| D8 | Agent time budget (the cutoff) | 3600 s by default, at most 14400 s; another number is justified in the pull request that sets it; one number within a benchmark and mode unless that pull request says why (§2.12), always the same in a task's privileged and standard versions (§2.15), and results are grouped by budget. No benchmark has an exception to the cap (§2.3). Each task sets its own, `[agent] timeout_sec` in its `task.toml` (its author, or its benchmark's generator; no central table), and every instruction states it in one format, in its last section (§2.12; owner, 2026-10-11, 2026-10-12 and 2026-10-14). |
| D11 | Harness | Official results use Harbor's native agents only; no agent adapters, and no gateway that holds credentials or changes requests. The usage gateway (`scripts/usage_gateway/`) is allowed: it forwards model-API requests unchanged, records token usage, and refuses what a trial may not have: a request past the token budget (§5) and, since 2026-10-10, every request that is not a model-API call (§2.11). No tool that runs outside the trial's container is offered to the model (§2.11): official runs turn the harness's web search off (Codex `web_search = "disabled"`, Claude Code `WebSearch` and `WebFetch` disallowed; `scripts/run_agent_batch.sh` `WEB_SEARCH=disabled`, the default) and start the harness without account connectors, apps, plugins, image generation and cloud agents (Codex: with the same switch the runner sets those features to false in the run's `config.toml`, `scripts/codex_tools_off.py`). These run at the model provider, so no egress allowlist stops them (2026-10-02: Codex with a ChatGPT login searched GitHub by default; 2026-10-10: the same login handed the model 238 account connector tools, and 21 trials called them) |
| D12 | Mode naming | `mode ∈ {privileged, standard, standard-realtime}` (the third mode since v1.1, #86; named `standard-realtime` since v1.1.1, owner 2026-10-08, #97: it is standard mode's robot as a service on a clock that does not stop); the `tier` field is removed; every task directory ends in its mode: `-privileged`, `-standard` or `-standard-realtime`. More modes may be added by pull request, through the registry of §2.16 (owner, 2026-10-14). |

## Agent budget cap (§2.3)

**Agent budget cap.** `[agent].timeout_sec` is at most 14400 s in every task; no benchmark is excepted
(`ci_checks/check-task-fields.sh` and `ci_checks/check-cutoffs.py`, `scripts/task_conventions.py`
`CUTOFF_CAP`). An exception would be an owner decision, recorded here, in `docs/benchmarks/<bench>.md` and in both
checks; its budget would be uniform within the benchmark, in both modes, and its results compared only with results under the same budget (D8). A
standard sidecar's wall clock (`RCB_WALL_CLOCK_S`, `/spec.budget.wall_clock_s`) equals the task's cutoff, in every
benchmark (§2.12) [CI]. The token budget (D10) is unchanged. (RoboTangle's 21600 s exception, 2026-10-08, issue #87,
ended with its tasks on 2026-10-13: RoboARC replaced them at 10800 s, `docs/CUTOFFS.md`.)

## Reference solutions and egress (§2.7)

| A solution, or a pointer to one, anywhere the agent can reach (task image, base image, tooling, docs in the container). A pointer is anything that locates the solution of this task: a URL, a dataset or file name, a demonstration or episode id, the name of the upstream expert that produced the reference. Provenance is kept in `scripts/<bench>/` and the README, never in a file under `environment/` the agent reads | MUST NOT | [CI] for the task's own files (`ci_checks/check-agent-pointers.py`: hosts of code, data and video, `*_url` keys, dataset and demonstration file names, keys that name a demonstration or episode (`"demo": ...`, `episode_id`); text files and the string members of `.npz` archives, since 2026-10-14 (board 0105: DexJoCo's `instance.npz` named its demonstration)); [current] for images, reviewed when they are built. Upstream documentation inside a simulator image that names the benchmark's public datasets or checkpoints is not removed file by file: the allowlist of §2.11 makes them unreachable. Open (2026-10-10): RoboTangle's image; its tasks were removed on 2026-10-13, and RoboARC's image is built FROM it (docs/benchmarks/roboarc.md) |
| Upstream experts scrubbed from images (e.g. RoboTwin `play_once`) | MUST | [current] |
| Agent egress allowlisted in `task.toml` (the model APIs and, since 2026-10-11, the package registries), in every task (§2.11) | MUST | [CI] (2026-10-10; until then a SHOULD "when a solution is publicly downloadable", and RoboTwin, MuJoCo Playground's four Aloha / Panda pairs, RoboWits, RoboLab, BEHAVIOR-1K and RoboTangle were open) |

## External material and the network (§2.11)

### 2.11 External material and the network (2026-10-10, relaxed 2026-10-11 and 2026-10-14)
**Baseline and stricter task rules (owner, 2026-10-14).** The `## External material` words below are the baseline every
task carries. A task MAY add stricter requirements of its own on top of them, never looser ones: `[metadata.honour]
stricter = "..."` in its `task.toml`, which `normalize` renders right after the baseline as "Additional rules for this
task (stricter than the above): ...". Benchmark-level openings that predate this (the open-network RoboOlympics
families) stay as documented below.
An agent solves a task itself. It may install the packages it needs and read whatever is installed in its container; it should not look the task's solution up. This is
an honour rule (owner, 2026-10-11: "a soft constraint, a gentlemen's agreement"), backed by a network that reaches the
model API and the package registries and not GitHub, Hugging Face or the general web, where most of the benchmarks'
sources, demonstrations and trained policies are published (a few are on PyPI too: the table below). History: until 2026-10-10 six benchmarks left the agent's egress open and three instructions
stated a rule; trials downloaded upstream sources, a reference solution, a recorded demonstration, robot models and
pretrained policies, from their own shell or through tools of the model's account. #150 closed the egress to the model
APIs and forbade every download and install, with "a result obtained with external material is void"; the owner found
that too strict: installing a package or trying a tool is part of what a model can do. On 2026-10-14 (owner, board 0107
E4) reading the installed environment, the simulator's and the benchmark's own source included, became explicitly
allowed: the rule forbids only searching the web for, or downloading, a ready-made solution. What the image ships is
therefore fair game, which is why it must hold no answer (§2.7, [LEAKAGE.md](LEAKAGE.md)).

| Item | Level | Basis |
|---|---|---|
| The agent may install packages (pip, apt) and use them, and may read anything installed in its container, the simulator's and the benchmark's own source code included (since 2026-10-14; before, the benchmark's source was on the list below). It does not search the web for, or download, a ready-made solution to the task: published or reference solutions, recorded demonstrations, policies trained for the task | honour rule | stated in every instruction; not enforced beyond the network below |
| A trial that fetched a solution is flagged and the owner decides, case by case; there is no automatic rule that voids it. Installing a general-purpose package is never a violation, and neither is a tool call or request that was refused (an attempt: flagged for a look, nothing more) | MUST (how results are judged) | [new] |
| `[agent] network_mode = "allowlist"` in every task, `allowed_hosts` = `scripts/set_agent_egress.py` `HOSTS`, the same list in every task: the model APIs' hosts and the package registries (`PACKAGE_HOSTS`: PyPI and the Debian / Ubuntu apt archives the images' distributions use). GitHub, Hugging Face and the general web are not on it | MUST | [CI] |
| The list is the one switch: what agents reach changes by editing it there (and a run without any restriction is `set_agent_egress.py public` on a copy of the tasks, docs/RUNNING.md) | MUST | [new] |
| What the task itself needs at run time (assets, robot models, the tooling's packages, caches) is in its image or the task directory; a task that needs a download during the agent phase does not conform | MUST | [current] (of the six benchmarks switched on 2026-10-10, RoboTwin, the Playground pairs, RoboWits, BEHAVIOR-1K and RoboLab were run with the oracle under the allowlist, both modes, with the rewards and state hashes of their open-egress runs; RoboLab needed its image to hold the materials it used to fetch, `eai-robolab:0.1.2`; RoboTangle, whose image documents that it needs no network, was not run again before its next release) |

**Per-benchmark exceptions.** A benchmark's agents have open egress, and its instructions say so, only by owner
decision, recorded here, in `docs/benchmarks/<bench>.md` and in the three lists that implement it (the same directory
prefix in each): `ci_checks/check-verifier-isolation.sh` `OPEN_EGRESS` (the task sets no `[agent]` network policy:
Harbor's default, open), `scripts/task_conventions.py` `EXTERNAL_OPEN` (the benchmark's own `## External material`
paragraph) and `scripts/set_agent_egress.py` `OPEN_EGRESS` (`allowlist` leaves these tasks alone). Its results are
compared only with results under the same network setting. The exception covers the benchmark's tasks that set no
`[agent]` network policy; a task of it that declares the allowlist (RoboOlympics' exported tasks, §4c) is an allowlist
task in every respect: the CI check holds it to the one host list, its instruction has the common `## External
material` paragraph, `allowlist` maintains it and the runner narrows its copy to the gateway.
- **RoboOlympics** (owner, 2026-10-11, as RoboFunOlympics, renamed 2026-10-14; `roboolympics-<family>-i<NN>`, its single-humanoid sports families, not its exported tasks (§4c),
  [`benchmarks/roboolympics.md`](benchmarks/roboolympics.md)): the agent may search for, download and use public
  tools, robot models and pretrained controllers (a published Unitree G1 walking, jumping or whole-body policy), and
  is encouraged to: finding existing work and adapting it to the robot is part of what these tasks measure. The honour
  rule that remains is not to look up a ready-made solution to the task, such as the benchmark's reference solutions
  (reading the benchmark's installed source is allowed, as everywhere since 2026-10-14). Nothing an agent can reach
  in the task or its image holds a solution, as everywhere (§2.7). An official run still goes through the usage gateway
  for the model API, and the runner leaves the rest of the egress open for these tasks. With open egress the gateway
  is no longer the only road to a model provider (the provider key is in the agent's container): its token accounting
  and its budget (§5) bind only what the harness itself sends, so these runs' usage is reported as harness-reported,
  and a trial that called a model API directly is flagged in review.

## Time cutoff (§2.12)

### 2.12 Time cutoff (2026-10-11; at the end of the instruction, 2026-10-12; each task's own, 2026-10-14)
Every task gives the agent a fixed wall-clock time, its **cutoff**, and tells the agent so in the last section of its
instruction, together with the request not to cheat, in one format in every task (owner, 2026-10-11, board 0080, issue
#156, after
Terminal-Bench's "You have 28800 seconds to complete this task. Do not cheat by using online solutions or hints specific
to this task."). Until then each benchmark stated its budget in its own words and place ("60 minutes", "1 h", "90 min
(5400 s)", a paragraph of its own in RoboDojo since #155; RoboTwin's privileged instructions not at all), and the number
was a constant, a data value or a literal in each of 26 generators.

| Item | Level | Basis |
|---|---|---|
| Each task sets its own cutoff: `[agent] timeout_sec` in its `task.toml`, a whole number of seconds within D8's cap (§2.3), set by its author in the pull request that adds or changes the task and stated in that pull request's Contract; a generated benchmark keeps its number as a constant of its generator (`scripts/<bench>/`). There is no central table (owner, 2026-10-14, board 0120: as in Terminal-Bench, whose tasks set `[agent] timeout_sec` and whose CI checks the instruction's closing sentence against it). From 2026-10-11 to 2026-10-14 one table, `scripts/task_cutoffs.toml`, held every cutoff; its record is in `docs/CUTOFFS.md` | MUST | [CI] (`ci_checks/check-cutoffs.py`, per task) |
| A benchmark uses one number for all its tasks of a mode; a pull request that gives some tasks another number says why (its overview lists the numbers it sets) | SHOULD | [review] |
| The `sim` service's own clock (`RCB_WALL_CLOCK_S`: `/spec.budget.wall_clock_s`, `meta.time_left_s`) reports the same number and ends nothing. It counts from the agent's first request to the service (any endpoint; logged, so a restarted service keeps it), never from the service's start or the end of its scene build: the sidecar is up before the agent's phase begins, and a clock started then runs ahead of the harness's (STANDARD_MODE.md, "The agent's clock"). So `time_left_s` never runs out before the cutoff, and the instruction tells the agent to plan by it. A service that ends the episode on its own clock says so in the benchmark's own text and keeps the earlier closing sentence: today RoboARC's, which since its MuJoCo release (2026-10-13) counts from the first request like the others and still ends the episode at 0 (its instruction says so); it becomes report-only at RoboARC's next task update (`docs/benchmarks/roboarc.md`) | MUST | [CI] for the number and the service layers' tests (`check-unit-tests.sh`); [new] (2026-10-13, owner; before, RoboCasa's three benchmarks and twelve `eai-standard/2.2` services, LabUtopia among them, counted from the service's start) |
| Changing a cutoff: an owner decision. Its pull request sets the new `[agent] timeout_sec` in the tasks concerned (a generated benchmark: the generator's constant, then a render), in both twins, normalizes them and states old -> new, who decided and why (label `cutoff-change`, approved by the owner). The task changes in place and keeps its name (§2.8); the pull request and the tasks' git history are the record, there is no Change Log entry in each task's README (owner, 2026-10-12); results recorded under another cutoff are reported separately (D8) | MUST | [new] |
| A new benchmark needs its label in `scripts/task_conventions.py` `BENCHMARKS` (task-directory prefix -> name), in its shared-files pull request (D6); its cutoff is in its own tasks | MUST | [CI] |


No benchmark keeps the earlier sentence today ("The service's `time_left_s` is its own count of this limit, from the service's start or from your first request, so it can differ from the time you really have left."): RoboARC's standard tasks did until its MuJoCo release (2026-10-13), whose service counts from the first request.

Seconds only, because the sentence is then the same in every task and the number is the one in `task.toml`; a second
unit is a second number to keep right. The sentence pair opens the section and the explanation follows it, because the
explanation refers to it; the two together are the end of every instruction. A heading of its own lets a benchmark's
text point to it from anywhere ("the time limit (`## Time limit`)") and keeps it apart from `## Resource limits`. Half
of the failed privileged trials recorded until 2026-10-11 ended at the cutoff, which is why the section also says what
is graded then.

**What follows a cutoff and what does not.** `normalize` rewrites everything that follows the task's number (above)
and its digest; [`CUTOFFS.md`](CUTOFFS.md) explains the rules and keeps the history of the table. A scheduler's
estimate of a trial's length reads `task.toml`. Not derived from the cutoff: the token budget (§5), the resource limits
(§2.10), reset budgets (§4.5), step caps, verifier timeouts. Collect-hook and verifier budgets that were sized for an
episode as long as the agent's time (RoboCasa's three benchmarks, RoboLab, YAMLab, DexJoCo, BEHAVIOR-1K) hold for any
shorter cutoff and are looked at when one is raised.

## Seeds (§2.13)

The owner, 2026-10-13: "every task needs a default seed, but may also allow a change of seed, or name a list of seeds
it allows, so that the task's submitter verifies which seeds are reasonable"; "we do not want the agent to memorise
the answer: a reference solution can be the solution of one seed; from now on the answers are per seed"; "the seeds
can be a list, a range, or any seed"; official batches draw a seed from the allowed ones for each trial. A seed names
one instance of the task (its scene and start, replayed bit for bit as before); where an upstream has no seed of its
own, seed 0 names the task's one frozen instance.

Until a benchmark's generator writes more, every task allows its default seed only (`allowed = [default]`): the 2026-10-13
migration changed `task.toml` only (the instances, the instructions and the READMEs are unchanged).

## Scene dynamics (§2.14)

The owner, 2026-10-14: "every task runs in standard mode by default; a subset, the dynamic tasks, gets a
standard-realtime mode as well". A task is **dynamic** when something in its scene other than the robot can do work by
a force other than the robot's own and gravity ("非机器人力和重力原因下能够做功的"): a body that starts with a velocity
(a thrown, served, rolling or sliding object; a pendulum already swinging), an actuated or scripted body (a conveyor, a
motor-driven rail or turntable, a scripted push, a timer that moves a part), an opponent or another agent. Everything
else is **static**: the world waits while the agent thinks, and objects move only because the robot moves them or
gravity pulls them. Decided with it (board 0106, owner 2026-10-14):

- settling under gravity after reset, cloth / liquid / granular material the robot moves, a falling domino chain the
  robot started: static (gravity does the work);
- passive springs, joint stiffness and elastic material that only give back what the robot put in (a spring button, a
  self-closing latch, a springboard, an elastic rope): static;
- a world change applied once and instantly when the robot comes near (LIBERO-MAX's on-proximity relocations): static;
  a change on a clock, or a mechanism that keeps moving bodies after the robot started it (a venue that launches a
  ball at t = 2 s, a goalkeeper that moves after the kick, a timer dial that turns back by itself): dynamic;
- visual-only or state-only change (a faucet's water and a burner's flame drawn as a site, cooking and freezing
  states, an on/off flag): static;
- an episode horizon or step cap is not a force: static;
- a robot that must balance actively (a floating-base humanoid or legged robot, a hovering drone) does not make a task
  dynamic by itself (owner, 2026-10-14: HumanoidBench needs no realtime mode by this definition).

## Modes a benchmark ships (§2.15) and cutoffs of a new mode (§2.16)

A benchmark may ship **any subset** of the three modes: privileged only, standard only, standard-realtime only, or any
combination, and a family within a benchmark may lack a mode its benchmark has (RoboDojo's six standard-only tasks,
§4.8). No owner decision is needed for the choice; what a benchmark leaves out is stated in its doc. This general rule
replaces the per-benchmark exceptions that allowed a missing twin before (RoboOlympics without privileged mode, §4b,
owner 2026-10-08; RoboDojo's six, §4.8, owner 2026-10-11); those benchmarks are unchanged and conform.

**Cutoffs of a new mode.** A task of the mode sets its own cutoff like any task (§2.12). Whether it must
equal another mode's number is the registry's `same_cutoff_as`, decided in the mode's pull request: standard has
`same_cutoff_as = "privileged"` (owner, 2026-10-12, CI-enforced), standard-realtime has none (today its numbers equal the
others everywhere). A new mode is free unless its pull request says otherwise.

## Privileged mode (§3)

| Item | Level | Basis |
|---|---|---|
| Exception, one replay: a benchmark whose tasks are measured to replay bit for bit may be graded by ONE fresh-process replay, to save grading time (`success` = that replay's success). Nothing is compared then, and `reward.json` says so: `deterministic = 1` with `determinism_checked = 0` and `replays = 1`. The replay must start from the frozen state, shown by the recorded initial-state hash: a rebuilt instance that hashes differently gives no verdict (`instance_mismatch` with `infra_error`). The benchmark's doc states the rule, the measurement behind it and what it gives up (a trajectory whose outcome differs between fresh processes is no longer caught). RoboDojo, its 48 privileged tasks ([`benchmarks/robodojo.md`](benchmarks/robodojo.md)) | MAY, by owner decision | [new] (owner, 2026-10-12) |
| A hash check before moving to new hardware; a host that rebuilds a different state is graded `instance_mismatch` with `infra_error` (privileged: also when no trajectory was handed in; standard: the service's `reason`). A scene build must not depend on the host: no unsorted directory listing, no wall clock. RoboTwin's `place_a2b_left`, `place_a2b_right`, `place_object_scale` and `place_object_stand` drew their object from an unsorted `glob` (directory order) and never rebuilt off the reference workstation; since 2026-10-14 the tooling sorts it and their instances are re-frozen (board 0113) | SHOULD | [current] |

## Standard mode (§4)

| Version | Date | Content |
|---|---|---|
| eai-standard/2.1 | 2026-09-30 | the base (formerly `rcb-limited/2.1`): no reset; `/submit` action chunks, `/observe`; binary RCB1 responses; 82-column proprioception, optional depth noise; crash recovery. Served by the standard tasks of RoboTwin, DexToolBench, MuJoCo Playground (manipulation), KinDER, HumanoidBench, MetaWorld+, VLABench, the three RoboCasa benchmarks, LIBERO-MAX, BiGym 2.0, RoboOlympics, RoboFunOlympics, RoboSafeBench |
| eai-standard/2.2 | 2026-10-01 | additive extension (§6, [`STANDARD_MODE.md`](STANDARD_MODE.md) Part 2) with crash recovery; served by BEHAVIOR-1K, RoboLab, RoboWits, RoboPaint, MolmoSpaces, MyoSuite, DexJoCo, YAMLab, RoboDojo, ManiGuard, Panda Dynamic Scenes, DexHand and MuJoCo Playground's quadruped tasks (LabUtopia and AutoBio until their removal on 2026-10-14) |
| eai-standard/2.3 | 2026-10-08 | 2.2 + the realtime capability (§4b; [`STANDARD_MODE.md`](STANDARD_MODE.md) Part 3, "Standard-realtime mode"); every 2.2 addition stays a MAY. Served by standard-realtime tasks only (HumanoidBench, BiGym 2.0, MyoSuite, RoboOlympics, RoboSafeBench, Panda Dynamic Scenes, RoboCasa365, MuJoCo Playground); standard tasks stay on 2.1 / 2.2. Issue #86 |
| eai-standard/2.4 | 2026-10-08 | 2.3 + the operations capability ([`STANDARD_MODE.md`](STANDARD_MODE.md) Part 4): operation ids and request deadlines (408 / 409), `GET /operations/<id>`, a service-owned call watchdog, a physics-tick ledger, fsynced journals; every earlier addition, the realtime capability included, stays a MAY. Served by standard tasks (Robo, RoboARC; first RoboTangle); reference implementation `scripts/eai_standard/v2_4/`. Issue #89 |

**Declared contact and safety telemetry** (owner decision, 2026-10-10). The MUST NOT on object contact forces has one
documented exception: a benchmark may publish contact or safety telemetry in standard mode when its task contract
depends on it (the agent is judged, or its success is held for review, on a reading it could not know otherwise), and
`docs/benchmarks/<bench>.md` declares exactly which fields are published and why. Nothing but the declared fields is
published; object poses, scene files, seeds, the success predicate and segmentation stay MUST NOT, and a reading that
gives an object's pose is not covered. Benchmarks that use it are listed here.
- **RoboARC** (standard tasks): `meta["safety"]` of every response: the forcing record (the largest force an arm
  or a part it holds pressed with, the drive load meanwhile, forcing events), the deepest task contact and
  held-finger contact with their review limits, the review events (with the names of the parts in contact), the lowest soft-body volume ratio and the worst cord
  attachment stretch, the table-guard stops and IK jumps
  ([`benchmarks/roboarc.md`](benchmarks/roboarc.md), "Safety readings in standard mode"). The benchmark's
  physical-validity policy holds a success with a deep contact for human review and ends an episode on a collapsed soft
  body, so the agent must be able to see the reading it is judged on.

**Per-benchmark reset defaults.** A benchmark's standard or standard-realtime tasks may default to a reset budget N > 0 only by owner
decision, recorded here and in `docs/benchmarks/<bench>.md`; the capability is the one above (`POST /reset`, only the
last episode graded, a success ends the trial: [`STANDARD_MODE.md`](STANDARD_MODE.md)), the budget stays an override (`RCB_RESET_BUDGET`), and that benchmark's
results must state the reset budget and are compared only with results under the same budget.
- **HumanoidBench** (owner, 2026-10-07; its standard-realtime tasks too, 2026-10-08): `budget.reset = 50`. The H1 falls within 1–3 s of robot time and the agent has
  no simulator to practise in, so a single episode is one blind attempt. `RCB_RESET_BUDGET=0` still runs one episode;
  HumanoidBench standard results recorded before 2026-10-07 ran with 0 and are reported separately
  ([`benchmarks/humanoidbench.md`](benchmarks/humanoidbench.md)).
- **RoboOlympics** (owner, 2026-10-12, as RoboFunOlympics; its single-robot sports families):
  `budget.reset = 50`, HumanoidBench's value for the same reason. A sport is attempts: a jump, a throw or a kick is over
  in a second or two and ends at the first foul or fall, and the agent has no simulator to practise in. `RCB_RESET_BUDGET=0`
  still runs one attempt ([`benchmarks/roboolympics.md`](benchmarks/roboolympics.md)).
- **MyoSuite** (owner, 2026-10-09; standard tasks; its standard-realtime twin has the mode's default, 10, too): `budget.reset = 10`. MyoSuite's own termination ends most episodes
  within a second or two of simulated time (a dropped object, an object off the reference motion), and the agent has no
  simulator to practise in, so a single episode is one blind attempt at muscle-level control. `RCB_RESET_BUDGET=0` still
  runs one episode; MyoSuite standard results recorded before 2026-10-09 ran with 0 (and saw the wrong `joint_effort`)
  and are reported separately ([`benchmarks/myosuite.md`](benchmarks/myosuite.md)).
- **BiGym2** and **KinDER** (owner, 2026-10-11; standard tasks): `budget.reset = 10`.
  The task's horizon (BiGym2: twice the longest human demonstration; KinDER: its 1000 control steps) bounds each
  episode, and with no reset the agent's practice and its graded attempt share it: of GPT-6 Astra's 16 standard runs,
  12 failed, 10 of them with the steps spent and 2 on an object on the floor, the hour mostly unused. Ten, as
  MyoSuite, not HumanoidBench's 50: an episode here is long. Steered call by call, one took Astra 6–50 min (median
  19), so ten resets leave the wall clock the only limit; a script that only replays actions ends one in about a minute
  (BiGym2 pick-box's 4400 steps in 75 s, KinDER sweep-simple's 1000 in 64 s, a reset about 1 s; RTX 4090,
  2026-10-10), so with 50 it could spend the hour on some 50 tries, and any success ends the trial.
  `RCB_RESET_BUDGET=0` still runs one episode; standard results recorded before this change ran with 0 and are
  reported separately ([`benchmarks/bigym2.md`](benchmarks/bigym2.md), [`benchmarks/kinder.md`](benchmarks/kinder.md)).
  BiGym2's standard-realtime tasks keep 0.
- **DexToolBench** (owner, 2026-10-13; standard tasks): `budget.reset = 20`. With one episode the first grasp decided
  the trial: all 21 of GPT-6 Astra's standard trials (2026-10-12) knocked the tool off the table at some point, the one
  success included, most of the hour went into picking it up from the floor, and the same task gave unrelated results
  from one run to the next (board 0098). A reset puts the robot, the tool and the goal sequence back to the frozen start
  (the service's `Session.reset()`; the same state hash, images and proprioception). The MuJoCo service
  (`images/mujoco/limited/server_mj.py`) implements the capability as above; its other tasks (MuJoCo Playground ALOHA,
  Panda) keep 0. `RCB_RESET_BUDGET=0` still runs one episode; DexToolBench standard results recorded before this change
  ran with 0 and are reported separately ([`benchmarks/dextoolbench.md`](benchmarks/dextoolbench.md)).
- **MuJoCo Playground, quadrupeds** (owner, 2026-10-14, board 0113; the nine `mujoco_playground_{go1,spot,barkour}_*`
  standard tasks): `budget.reset = 10`. A fall, a failed turn or a wrong first chunk used to end the trial. A reset
  restores the frozen start (`rcb_quadruped.Session.reset()`: the same state hash and proprioception). The quadrupeds'
  2.2 service (`scripts/mujoco-playground/shared/standard/server.py`) implements the capability as above, as MyoSuite's
  does (its instruction calls `POST /reset` through `Robot._post`). The ALOHA and Panda standard tasks keep 0.
  `RCB_RESET_BUDGET=0` still runs one episode; quadruped standard results recorded before this change ran with 0 and
  are reported separately ([`benchmarks/mujoco-playground.md`](benchmarks/mujoco-playground.md)).
- **DexHand** (owner, 2026-10-14, board 0109; standard tasks, from their first release): `budget.reset = 20`,
  DexToolBench's value. Every family ends an episode at the first failure (a dropped, slipped or knocked object, a bound
  exceeded), the essential families start with the object already in the hand, and the agent has no simulator to
  practise in, so with one episode the first slip decided the trial. A reset calls the family's `Session.reset()` (the
  same state hash as a fresh process). The DexHand 2.2 adapter (`scripts/dexhand/shared/standard/server.py`) implements
  the capability as MyoSuite's does. `RCB_RESET_BUDGET=0` still runs one episode
  ([`benchmarks/dexhand.md`](benchmarks/dexhand.md)).

| Item | Level | Basis |
|---|---|---|
| Exception, physics that does not replay bit for bit: a task measured not to (its frozen instance records it and why, e.g. `"determinism": "verdict"`; the benchmark's doc names the tasks and the measurement) is graded by the live episode the trusted service ran, `success = live_success`, read from the sim sidecar's own record of that episode (`final.json`; nothing the agent's container writes is read); the fresh replays still run and are reported (`replay_success`, `state_identical`, `deterministic`) but never decide, a replay without a result does not void the live verdict, and `reward.json` says `graded_by_live = 1`. A missing live record stays `infra_error`; an episode resumed after a crash (§4.7) is graded on its live state after the resume, so `reward.json` reports `resumes` and `resume_state_mismatch` and results state them. Such a task is standard-only: an open-loop trajectory of it cannot be graded reproducibly, so its family ships no privileged task (§2.15; `scripts/task_conventions.py` `NO_TWIN` lists these tasks with that reason). The verifier still grades `final.json` only, so §2.6's same verdict in a fresh process holds. RoboDojo: 6 tasks (two cloth, three liquid, `make_toast_random`) | MAY, by owner decision | [new] (owner, 2026-10-11) |
| Exception, one replay (the same decision as §3's): a benchmark whose tasks are measured to replay bit for bit may replay the recorded episode ONCE in a fresh process, and one successful replay is enough: `success = live_success ∧ replay_success` (the live predicate is then required, not SHOULD: it is what guards against a replay that succeeds where the episode did not, as the replay guards against a live success that does not repeat). `deterministic` is still measured, the replay's end state against the live episode's (= `state_identical`, `live_matches_replay`; `determinism_checked = 1`, `replays = 1`), and reported, but does not decide. A replay without a result, or one that did not start from the frozen state, stays `infra_error`. A task graded by the live episode (the exception above) records one replay instead of two. RoboDojo, its 54 standard tasks ([`benchmarks/robodojo.md`](benchmarks/robodojo.md)) | MAY, by owner decision | [new] (owner, 2026-10-12) |

### 4.9 Live recording (sidecar only)
`live.mp4`, `live_timeline.jsonl`, `live_segments.jsonl`, `trajectory_live.f64`, `startups.jsonl` — SHOULD
(implemented for RoboTwin). If recorded: rendered from the replay by default, frames stamped with the call, never
affecting the verdict.

## Standard-realtime mode (§4b)

| Item | Level | Basis |
|---|---|---|
| How well the clock was kept is evidence in `final.json`, and the grader repeats it in `reward.json` as numbers (a missing one is 0): `clock_s` (wall seconds the clock ran, over the trial), `max_lag_s` (the furthest a control step ran behind its time), `stalls` (the times the service, more than 0.5 s behind, dropped the debt instead of fast-forwarding the robot), `stalled_s` (the wall time dropped that way: the robot stood still while its clock should have run), `stalled_share` = `stalled_s` / `clock_s`, `held_steps`, `late_steps`, and what the requests cost: `requests_refused` (answered 4xx), `request_busy_s` (simulator-thread time spent on requests). They decide no verdict: a trial whose clock stalled is flagged by these fields, not failed or voided (whether a stalled trial counts is an open owner decision) | SHOULD | [new] (v1.2-rc: review R2 M1; before, only RoboOlympics' grader exported `stalls`, and `max_lag_s` never passed 0.5) |
| What a request can cost the clock is bounded by the service: the body is read, decoded and checked off the simulator's thread, so a refused or malformed request never reaches it (a body with more than 1 MiB of JSON text is parsed by a separate process; the 64 MB limit of §4 stands); behind the clock, control steps run before waiting requests, which are served once it has caught up (they queue behind each other: an `/observe` may take longer to answer, the robot's time does not slow down), and a rendering request that is a stall by itself (more than 0.5 s) holds the next one back four times as long, so requests take at most a fifth of the clock's time; and the cameras are rendered at most once per control step however many requests and watches ask | SHOULD | [new] (v1.2-rc: review R2 M1) |
| Slowdown S: `RCB_SLOWDOWN`, its default set per task and **stated in the task**: `[metadata] slowdown` in `task.toml` (written by `scripts/task_conventions.py` from the sim service's `RCB_SLOWDOWN` default), the README's "Real time" row and the instruction (`S = <S>`). A twin made for a `dynamic` family (§2.14) takes S from the real-time factor RTF of its own service, measured on the reference workstation (robot seconds per wall second with the clock running flat out, `RCB_SLOWDOWN` ≪ 1, CPU-capped as in its compose file): **S = 1 when RTF ≥ 3**, else S ≈ 1.5 / RTF rounded up, so that the clock needs at most two thirds of what the simulator can do (owner, 2026-10-14, board 0112); the benchmark's doc records the measurement. S = 1 is real time; RoboOlympics' 10 is its own (below). Results with S ≠ 1 are reported separately from S = 1 and state S; official results use the task's S | MUST | [CI] (`ci_checks/check-realtime.py`, 2026-10-14) |
| Reset budget: every standard-realtime task allows resets, **10 by default** (`budget.reset = 10`; owner, 2026-10-14: "all realtime tasks allow resets"): an episode on a clock that does not stop is one attempt, often over in seconds, and the agent has no simulator to practise in. Per-benchmark exceptions only as in §4.5: HumanoidBench 50; BiGym 2.0 0 (its twins stay as they were, owner 2026-10-14); RoboOlympics 0 (a match is one episode); RoboSafeBench 0 (a safety episode is one attempt: a harm done cannot be reset away, and its standard tasks have no reset either; board 0114, confirmed by the owner 2026-10-14). The reset capability is §4.5's; `RCB_RESET_BUDGET` overrides it; results state the budget and are compared only under the same budget | MUST | [CI] (`ci_checks/check-realtime.py`, 2026-10-14; before: no reset by default, v1.1.2, #102) |

**Per-benchmark exceptions.** A benchmark's standard-realtime tasks may differ from a default or a MUST of this section
only by owner decision, recorded here and in `docs/benchmarks/<bench>.md` (and, where CI checks the rule, in its
exception list), in the same way as HumanoidBench's reset budget (§4.5). The
interface, the encoding, crash recovery and the evidence are never excepted: every standard-realtime task serves
`eai-standard/2.3`, except the tasks a benchmark exports with its own service (§4c). That benchmark's results state what differs and are compared only with results under the same
settings.
- **RoboOlympics** (owner, 2026-10-08): its three tasks on this repository's 2.3 adapter (table tennis, badminton, air
  hockey; S = 10, no privileged twin) were removed on 2026-10-14 (owner, board 0107 E7), and with them this exception.

## Tasks a benchmark exports with its own service (§4c)

Owner, 2026-10-14 (board 0107, E7): a benchmark that has its own task runtime (simulator service, referee, opponents,
grader) may ship tasks its own exporter writes, with that runtime unchanged inside the task, instead of this repository's
`eai-standard/2.x` layer. The task is a plain Harbor task in every other respect: §1, §2 (verifier isolation, honour
rule, egress, cutoffs, resources and limits, seeds, README) hold. First and so far only: RoboOlympics, 8 tasks
(`scripts/roboolympics/exported.toml`; [`benchmarks/roboolympics.md`](benchmarks/roboolympics.md), "Tasks exported by
RoboOlympics").

| Item | Level | Basis |
|---|---|---|
| `metadata.protocol` names the benchmark's protocol and its version, per mode: RoboOlympics `eai-standard-realtime/1.0` (matches, `standard-realtime`) and `skilleval-api-test/1` (skill tasks, `standard`, `task_type = "policy"`); its wire format is documented in the benchmark's doc and in the instruction, not in [`STANDARD_MODE.md`](STANDARD_MODE.md) | MUST | [CI] (protocol) |
| Real-time matches: the world runs at 1/S of real speed, S per task (the sport's official slowdown: RoboOlympics table tennis 10, badminton 20, humanoid soccer 5, wheeled soccer 10; `metadata.slowdown`); a command takes effect at the next control step and all agent latency counts; after every point the world may freeze for a bounded review (at most 300 s; a rule of the sport, the agent's `ready` ends it early; as implemented, and stated in the instructions since 2026-10-14: a side that has not sent `ready` within the limit, 300 s or 600 s in soccer, loses the match, `ready_timeout`) while the agent's time budget runs on | MUST | [new] |
| Opponents are scripted, at a fixed level per task (`metadata.opponent_level`); success = the match is valid (the fresh replay repeats the live state, scores and winner) and the agent's side won | MUST | [new] |

- **RoboOlympics** (owner, 2026-10-08; `roboolympics-<sport>-<format>-i<NN>-standard-realtime`, real-time sports
  against a scripted opponent, [`benchmarks/roboolympics.md`](benchmarks/roboolympics.md)):
  - slowdown: `RCB_SLOWDOWN` defaults to **10**, RoboOlympics' official slowdown of these sports (a rally is over in a
    few seconds, faster than a model's turn); it stays an override, and the results state S and are reported
    separately (as every S ≠ 1).
  - no privileged twin (not an exception since 2026-10-14: a benchmark ships any subset of the modes, §2.15): the
    sports measure play from camera images against an opponent; there is no trajectory deliverable.
  The breaks between points are part of the sports' rules, not a protocol feature: the clock never stops (the match
  stands still for a bounded time while the control steps go on, and the agent's `ready` command ends a break early; as implemented, a missed `ready` within the limit loses the match, `ready_timeout`, stated in the instructions since 2026-10-14).
- **RoboSafeBench** (requested by the authors 2026-10-14, accepted on review, board 0114; `cell-<slug>-i<NN>-standard-realtime`,
  [`benchmarks/robosafe.md`](benchmarks/robosafe.md), "Standard-realtime tasks"):
  - no privileged twin (not an exception since 2026-10-14: a benchmark ships any subset of the modes, §2.15; here a
    privileged agent holding the simulator would read the hazard state, so RoboSafeBench ships standard and
    standard-realtime only): each realtime task carries its standard task's instance under RoboSafeBench's realtime
    clock (its own start hash) in the sim sidecar.
  - pictures while the clock runs: the scene is rendered on the CPU (about 0.2 s a picture) by the simulator's thread.
    Each picture a response carries is charged a fixed 0.24 s of robot time (the render's own wall time forgiven), so
    the world moves on by the same amount whatever the host; a request returns pictures of at most 2 cameras and a watch
    at most 2 pictures per second and no depth (`/spec.timing`; the rates above stalled under sweep load, the benchmark's
    doc). Before the clock starts pictures cost nothing and every request may ask for every camera.
  Everything else is this section's: S = 1 (RTF 3.4 measured on the reference workstation, the 6-CPU cap, `RCB_SLOWDOWN`
  = 0.01, `cell-c01-i00` reference; the benchmark's doc), no reset (the exception in the reset row above), the
  service's evidence and stalls counted, never deciding.

## Versioning (§6)

**`eai-standard/2.4`** (2026-10-08, issue #89; [`STANDARD_MODE.md`](STANDARD_MODE.md) Part 4). 2.3 plus the operations
capability: `meta.operation_id` and `meta.request_deadline_unix_s` on `/submit` and `/observe` (408 for an expired request,
409 for an id already admitted: a call is never executed twice), `GET /operations/<id>` (`admitted`, `completed`, `error`,
`interrupted` with `execution_uncertain` after a crash), a service-owned watchdog that ends a hung native call as an infra
error, a physics-tick ledger that resumes replay with the ticks each row took, and fsynced journals. Every earlier addition
(2.2's, and 2.3's realtime capability) stays a MAY, so a 2.2 service with the operations capability is a 2.4 service;
standard tasks may declare it, standard-realtime tasks stay on 2.3. The reference implementation is `scripts/eai_standard/v2_4/`
(`rcb_limited.py`, `rcb_client.py`; `rcb1.py` and `run.sh` are 2.2's), copied unchanged into every 2.4 task. First
served by RoboTangle, whose release named it "2.3" before that number went to the realtime capability.

## Migration status (§7) as recorded until 2026-10-14

## 7. Migration status

The v1.0 migration of the existing tasks (mode names and suffixes, `oracle` fields, `/logs/verifier` cleared first,
numeric rewards, one README layout, no `results/`, generators ending in `scripts/task_conventions.py`) was completed on
2026-10-01; it changed task digests but no scene, instance or success rule. The open items keep their numbers: tasks
and documents cite them.

Open:
1. ~~Images~~ done 2026-10-02: every base image is `ghcr.io/mll-lab-nu/eai-<name>`; public unless `BUILD_ONLY`
   (RoboLab, BEHAVIOR-1K: private packages); RoboCasa365 and VLABench stay private until their asset licences are checked.
2. Pinned pip versions in the standard-mode client image and the MuJoCo image; one digest-pinned client image.
3. The results pipeline publishes to the results site, and applies the token budget after the run for runs without the
   usage gateway (with it, the budget is enforced during the run, §5).
4. Solvability: tasks whose `oracle_evidence` is "none known" (18 directories on 2026-10-10: six HumanoidBench
   families in their three modes; KinDER's tasks all name a passing privileged trajectory since #134) and the 15
   DexToolBench `partial` pairs (whose reference policy reaches only part of the goals, so it scores 0) have no verified
   positive example. Until they get one, results report them separately from the tasks with a verified solution.
5. ~~Agent egress~~ decided 2026-10-10 (owner, board 0072; it replaces "kept as it is" of 2026-10-02): every task is
   on the allowlist and every instruction states the external-material rule (§2.11). RoboTwin had been set back to open
   on 2026-09-24 and MuJoCo Playground's manipulation pairs, RoboWits, RoboLab, BEHAVIOR-1K and RoboTangle were added
   open, none for a stated technical reason. One had a dependency nobody had recorded: RoboLab's asset library fetched
   MDL materials and textures from NVIDIA's Omniverse content bucket at every scene build (without them its tables
   render red); image 0.1.2 holds them, and RoboLab's tasks moved to it with this change (rendering equal to the
   open-egress one within render noise, physics unchanged). An in-place change of every task's
   `instruction.md` and of 542 `task.toml` (scenes, instances, tooling and pass rules unchanged). Results obtained with
   open egress stand; the trials found to have fetched a solution or task sources were withdrawn and run again by the
   owner's decision of that day (RoboTangle as a whole). 2026-10-11 (owner): the rule becomes an honour rule and the package registries (PyPI, the Debian /
   Ubuntu apt archives) are reachable from every task, so that an agent can `pip install` and `apt-get install` as it
   could on the open tasks before (§2.11; an in-place change of every `task.toml` and `instruction.md` again; trials
   run between the two changes, under the model-APIs-only list, could install nothing). Open: RoboTangle's image still named upstream demonstrations and solution sheets in files a
   privileged agent can read (unreachable under the allowlist). Its tasks were removed on 2026-10-13; RoboARC's image is
   built FROM that image (docs/benchmarks/roboarc.md).
6. Resource limits (§2.10, v1.1.5): every task declares limits and caps and its `instruction.md` states the limits (an
   in-place change of every task's `task.toml`, `instruction.md` and README, 2026-10-10); BEHAVIOR-1K's compose files
   default `RCB_TEXTURE_BUDGET` to 0.1 (what every official run already used), so that Isaac's GPU memory does not grow
   with the card (owner decision). Scenes, instances and success rules are unchanged; results obtained before stand and
   are not re-run (they carry the label "limits: none"). v1.2 (owner-approved exception to §2.8): the generators add the
   monitor sidecar, the caps and the verifier step to the `environment/` and `tests/` of every published task in one
   migration. It landed on 2026-10-10 (#131, v1.2-rc): every task's `environment/docker-compose.yaml` (the `rcb_monitor`
   service, the beacon volumes, the caps), `environment/rcb_monitor/`, `task.toml` (the record as an artifact, the seal
   hook, `[verifier.env]`), `tests/rcb_limits.py`, `tests/rcb_limits.json`, `tests/Dockerfile` and `tests/test.sh`
   changed in place, enforcement off by default; task names, scenes, instances and success rules are unchanged and
   earlier results stand. The review fixes of the same day (board 0067) changed the same files again and
   `[environment].memory_mb` of the tasks whose declared cap for `main` was above it (the kernel's cap is now the
   declared one, above the limit), the README's limits line and the prompt's paragraph (host protection), and took
   RoboPaint's privileged `scorer` service, the benchmark's own, out of the limits' scope (recorded only; the memory
   limit of those tasks is 16 GiB instead of 21, the whole trial's expected peak stays 21); with enforcement off none
   of this changes a verdict. RoboLab, YAMLab, ManiGuard and LabUtopia have no texture-budget knob
   in their tooling yet, so their GPU limits rest on card-sized peaks until the calibration batch.
   Findings: agents installed nothing and cloned nothing in 423 recorded trials; the one observed leak was the
   harness's web search (now off, §5); PyPI is not neutral (the `metaworld` wheel ships every task's scripted expert).
7. Time cutoffs (§2.12; owner, 2026-10-11 and 2026-10-12, board 0080): every task's `instruction.md` changed in place
   (the closing `## Time limit` section; each benchmark's earlier statements of its budget reworded to "the time limit
   (`## Time limit`)"), and the 225 standard tasks whose `sim` service took its reported wall clock from a code default of 3600
   (RoboTwin, DexToolBench, MetaWorld+, RoboCasa's three benchmarks, MuJoCo Playground's four manipulation twins) got
   the line `RCB_WALL_CLOCK_S: "3600"` in `environment/docker-compose.yaml`: the same value, now written from the
   table. No cutoff changed; scenes, instances, tooling, services and success rules are unchanged, earlier results
   stand, and trials started before the change read the earlier wording. The generators' own copies of the number
   are gone. Stricter values are set in the table afterwards, by owner decision, each with its `[[history]]` entry.
   RoboTangle's standard service ended the episode on its own wall clock, started with the service, a little before
   the agent's session; its tasks were removed on 2026-10-13. RoboARC's service, which replaced them, counts from the
   first request (item 8) and becomes report-only at RoboARC's next task update (docs/benchmarks/roboarc.md).
8. The agent's clock in the standard modes (§2.12; owner, 2026-10-12, boards 0085 and 0087; landed 2026-10-13): every
   service's `meta.time_s` / `meta.time_left_s` count from the agent's first request to the service, and a resumed
   service keeps that moment (STANDARD_MODE.md, "The agent's clock"). The services that counted from their own start
   changed in place: RoboCasa, RoboCasa365 and RoboCasa-GR1 (`environment/sim/server_casa.py`: from the container's
   first start) and the twelve benchmarks on the shared `eai-standard/2.2` layer whose adapter counted from the
   service's start or readiness (BEHAVIOR-1K, RoboLab, RoboWits, RoboPaint, ManiGuard, MolmoSpaces, MyoSuite, DexJoCo,
   YAMLab, RoboDojo, LabUtopia, AutoBio: `environment/sim/rcb_limited.py`, `server.py`, and the client's docstring).
   RoboTwin, DexToolBench, MetaWorld+, MuJoCo Playground, KinDER, HumanoidBench, BiGym 2.0, VLABench, LIBERO-MAX and
   RoboOlympics already counted from the first request; their code is unchanged apart from the wording of `/spec`.
   Every standard instruction's closing `## Time limit` paragraph changed in place (what `time_left_s` counts from, and
   that the agent can plan by it), and the sentence "approximate: the harness's own deadline is authoritative" is gone
   from the instructions and `/spec` texts that had it (RoboTwin, DexToolBench, MetaWorld+, MuJoCo Playground). No
   service ended an episode on this clock (RoboTangle's apart, as in 7), so no verdict
   depended on it: scenes, instances, success rules and graders are unchanged and earlier results stand. What
   changes for an agent is that `time_left_s` no longer reaches 0 while it still has the harness's set-up time left (the
   service was up a median of 79 s before the agent's phase over 2,322 recorded standard trials, board 0085).

Decided (owner, 2026-10-02):
1. Success semantics stay benchmark-defined: each benchmark keeps its upstream's own rule (final state, first success,
   episode return, goal count), stated in its instructions and `docs/benchmarks/<bench>.md`; the protocol does not impose
   one rule across benchmarks.
2. Not yet implemented — standard-mode double check: the verifier replays the recorded `trajectory.npz` once more in its
   own sandbox; the sidecar's verdict stays authoritative, and a verifier replay that disagrees is reported as a warning
   (`replay_mismatch` in `reward.json`, a `WARNING` line in the log). Needs the standard verifier to use the simulator
   image (§2.4) and to read the trajectory (§4.8).
3. Kept as they are: one frozen instance per task (no per-run seeds), and what each benchmark exposes to the agent in
   privileged mode (no hiding of reward or success checks). Changed for seeds on 2026-10-13 (owner, §2.13): a task has
   a default seed and may allow others, each a frozen instance; the runner draws one per trial; reference solutions
   are per seed.

## v1.2-rc text not carried into v2.0 (2026-10-14)

As PROTOCOL v1.2-rc had them at `4a4014bf58`; their rules now live in RUNNING.md (runner configuration) and PROTOCOL
Appendix H. Kept here for the section numbers tasks cite.

### v1 §2.10 Resource limits (v1.1.5; judged inside the trial from v1.2)

A trial should not take more than its share of the machine. Every task therefore states **limits**, the most the agent
phase may use, shown to the agent in `instruction.md`. When enforcement is on, exceeding one is the agent's failure,
graded like a wrong deliverable. They sit between the minimums of §2.9 and the docker caps. All sizes are GiB.

| Item | Level | Basis |
|---|---|---|
| `[metadata.resources.limits]` and `[metadata.resources.caps]` with every field below | Default | [CI] |
| `scope = "trial"` in privileged mode, `"agent"` in the standard modes (the mode registry's field, §2.16) | Default | [CI] |
| `instruction.md` has `## Resource limits`, equal to what `task_conventions.py` renders, after `## External material` and before `## Time limit` | Default | [CI] |
| Relations: memory and GPU memory `min ≤ limit` (scope trial); `max_gpu_memory_gb > 0` only where the limited containers have a GPU; `trial_max_* ≥ min_*` and `≥` the limit (scope trial: equal, unless a benchmark-owned observe-only service exists); the scope's memory caps `≥ 1.2 × max_memory_gb` and `≥ max_memory_gb + 2`; `pids ≥ 8 × max_processes` for the bound services; a cap for every compose service (`rcb_*` helpers aside); every declared cap is the applied one (`caps.main` = `[environment]`, others = the compose file's `cpus` / `mem_limit` / `pids_limit`); scope agent: `max_memory_gb ≤ [environment].memory_mb / 1024`; `min_cpus ≤` the CPU caps of all services together; `verifier_min_memory_gb ≤` the memory caps of the sidecars a collect hook replays in | Default | [CI] |
| `measured` says what the values rest on; limits sit with a generous margin above measured peaks (e.g. `max(1.5 × peak, peak + 4 GiB)`) | Recommended | [new] |
| The oracle passes within the limits | Default | from v1.2 (the calibration batch) |
| Enforcement inside the Harbor trial (below) | Default | from v1.2 |
| Values uniform within a benchmark and mode (or family) | Recommended | [new] |

`[metadata.resources.limits]`:

| Field | Type | Meaning |
|---|---|---|
| `scope` | string | `"trial"` = every container the agent drives (privileged: `main` and any service it starts or controls). A service that is the benchmark's own and outside the agent's control (`BENCHMARK_SERVICES` in `scripts/rcb_monitor/inject.py`) is observed and recorded only; `"agent"` = the agent's container only (standard modes: the `sim` sidecar is recorded, never a failure) |
| `max_gpu_memory_gb` | float | GPU memory of the scope's processes, summed (NVML per process; what a process reserves counts); 0 = no GPU |
| `max_memory_gb` | float | memory of the scope's containers, summed (cgroup `anon + shmem`; without a cgroup, PSS) |
| `max_processes` | int | processes (thread groups) in the scope |
| `max_disk_gb` | float | growth of the files under `disk_paths` in the agent's container since the monitor's first complete measurement (before the harness is installed, so its install counts) |
| `disk_paths`, `disk_exclude` | list of strings | absolute paths measured / skipped (today `["/app", "/tmp", "/root"]` / `[]`); `/dev/shm` is memory |
| `sustain_sec`, `window_sec` | float | a violation: above a limit for at least `sustain_sec` in total within any `window_sec` (60 / 120 s); disk: two measurements in a row; gaps never count against the agent |
| `trial_max_gpu_memory_gb`, `trial_max_memory_gb` | float | expected peak of the whole trial, every container, for schedulers; not a failure condition |
| `measured` | string | provenance of the limits |

`[metadata.resources.caps]`: one inline table per compose service, `{ cpus, memory_gb, pids }`, the docker caps the
compose files apply; `main`'s CPU and memory caps are Harbor's `[environment]` values, so `normalize` sets
`[environment].memory_mb = caps.main.memory_gb × 1024` (the kernel's cap sits above the limit, so that the monitor sees
a violation before the OOM killer acts). CPU is never a limit, only a cap. An OOM kill by the kernel in a container in
scope, at that container's own cap, is a violation.

**A CPU cap above the host's CPU count means the host's count.** Docker refuses a container whose `cpus` exceeds the
machine's, so a runner clamps every CPU cap to the host's CPU count in the copy of the task it runs
(`scripts/clamp_cpus.py`, applied by `scripts/run_agent_batch.sh`); the task's files keep their values. Memory and pids
caps are never clamped.

**The switch.** `RCB_LIMITS_ENFORCE`, a run-time environment variable read by the monitor (compose default
`${RCB_LIMITS_ENFORCE:-0}`, so turning it on does not change the digest):
- `1` / `true` (hard): once the monitor confirms a violation, it kills the scope's processes and the verifier fails the
  trial: `reward.txt` = 0, `success = 0`, `success_before_limits` = the grader's verdict, `resource_limit_exceeded = 1`;
  never retried.
- `0` / `false` (default): observe and record only; the verifier reports peaks and violations
  (`limits_violation_observed`, `/logs/verifier/resource_limits.json`) and does not change the verdict, except that a
  benchmark-owned service killed for memory in an episode that did not succeed is `infra_error` (below). A missing
  record is only reported (`resource_monitor_missing = 1`).
- any other value: the monitor kills nothing and records a fatal event; the verifier reports `infra_error = 1`,
  `resource_switch_error = 1`.

**What fails a trial** (enforcement on) is exactly: a limit exceeded for `sustain_sec` within `window_sec` (disk: two
measurements in a row), or a kernel OOM kill in the scope at the container's own cap. Nothing another trial does on the
same host can.

**Out-of-memory kills.** The monitor reads each container's cgroup v2 `memory.events` (`oom_kill`, `oom`) in a thread
of its own, many times a second, until the record is sealed (the first collect hook), and records each kill with its
cause: `"cap"` when the container's own `oom` counter rose with it (or within 10 s before), else `"host"`. Then:
- a `cap` kill in the scope is the violation above (`over_oom = 1`, `resource_oom_kills`);
- a `host` kill in the scope is never a violation: with enforcement on the trial is not a result (`infra_error = 1`,
  `resource_host_oom = 1`), with it off it is reported and the verdict stands;
- a kill in a **benchmark-owned service** (a `sim` sidecar, a scorer) is recorded, never a failure; if the verdict is not
  a success, the trial is not a result (`infra_error = 1`, `resource_service_oom = 1`) in both settings. A success
  stands.

**Host protection** (enforcement on only), each an `emergency_kill` event, counted in `resource_emergency_kills`, shown
in `usage.json`, and never a violation by itself: GPU memory of the scope above 1.5 × `max_gpu_memory_gb` at one sample
kills the scope's process holding the most GPU memory; where the runtime applies no kernel memory cap, memory above the
sum of the declared caps kills the scope's largest process.

**Enforcement (v1.2).** Violations are judged by the Harbor trial itself, so every harness applies the same rule; a
trial a pool kills to protect its host is an operations abort (`killed_by_pool`), not a graded result.
- docker caps on every compose service;
- a monitor sidecar `rcb_monitor`, outside the agent's container, samples GPU memory, memory, processes, disk and OOM
  kills every few seconds into its own record (`rcb-monitor/1`), seals it in the first collect hook, and writes the
  current values to `/run/rcb-limits/usage.json` in the agent's container;
- the verifier recomputes violations from the raw samples with its own copy of the limits (`tests/`). A missing,
  unsealed, fatal or mostly empty record is `resource_monitor_missing = 1` (with enforcement on also `infra_error = 1`).

What the record can say: gaps never count against the agent, and more than 10 % of the agent phase unobserved makes
the record unusable; a disk walk that cannot finish is a gap whose partial sum is a lower bound; GPU samples NVML cannot
attribute per process (MIG, vGPU) are `gpu_unmeasured`, never a silent 0, and more than 10 % of them on a task with a
GPU limit make the record unusable.

The values live in `scripts/task_resources.toml` (`[[limit]]` and `[[cap]]` rules) and are written by `normalize`,
which also renders the paragraph and a README line; `ci_checks/check-resources.py` checks them.

**Rendered paragraph** (privileged; the standard modes say "Limits for your agent environment, your own container only
(the simulator in the `sim` service is the benchmark's and does not count)"):

> ## Resource limits
> Limits for the whole trial, all its processes together (every simulator you start included): at most **24 GiB of GPU
> memory**, **24 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`. GPU
> memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may
> be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process
> killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your
> container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on
> and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to
> protect the machine; that alone does not fail the trial. CPU is capped at 8 cores for your container; the cap only
> slows you down.

(The sentence about 1.5 times the GPU-memory limit is rendered only where the limits include GPU memory.)

### v1 §5. Results, cost, token budget
| Item | Level | Basis |
|---|---|---|
| Report success together with cost: tokens, money, turns, wall clock, simulation steps, calls | Recommended | [current] |
| Official results use Harbor's native agents (`-a codex`, `-a claude-code`, …), configured through environment variables | Default | [new] |
| Official runs go through the usage gateway, which forwards model-API calls only and is, with the package registries, the agent container's only egress; the harness offers the model no tool that runs outside the container (§2.11, D11). The runner flags a trial whose `totals.json` has `refused_paths`, `refused_server_tools` or `refused_bodies` | Default | [new] |
| **Token budget** per trial: input 100M (Harbor `n_input_tokens`, cache included), output 10M (`n_output_tokens`, reasoning included); exceeding either fails the trial; the results metadata records the budget and `over_token_budget` | Default | [new] (enforced while the gateway runs; otherwise open, §7 item 3) |
| Align reasoning effort, `max_turns`, token budget and `[agent].timeout_sec` before comparing agents | Recommended | [current] |
| Run id `<harness>-<model>-<effort>` | Default | [new] |
| Results are not committed: published on the results site and the Hugging Face dataset, keyed by run id | Default | [CI] for task directories |
| Results reported per mode; the standard modes state the protocol version and reset budget, standard-realtime also S | Default | [new] |

With the usage gateway on (`GATEWAY=1` in `scripts/run_agent_batch.sh`), once a trial's recorded input or output
reaches its budget the gateway refuses every further model request of that trial (HTTP 400, "token budget exceeded"),
the agent stops, and `<trial>/gateway/totals.json` records `over_token_budget = 1`. Budgets: `TOKEN_BUDGET_IN` /
`TOKEN_BUDGET_OUT`, default 100M / 10M. Without the gateway the budget would be applied after the run to Harbor's
counts; not implemented yet (§7 item 3).

### v1 §7. Migration status

The v1.0 migration (mode names and suffixes, `oracle` fields, `/logs/verifier` cleared first, numeric rewards, one
README layout, no `results/`, generators ending in `normalize`) was completed on 2026-10-01. The items keep their
numbers, because tasks and documents cite them; the record of each finished item (what changed in place, when, why) is
in [`PROTOCOL_HISTORY.md`](PROTOCOL_HISTORY.md).

Open:
1. ~~Images~~ done (2026-10-02): every base image is `ghcr.io/mll-lab-nu/eai-<name>`, public unless `BUILD_ONLY`.
2. Pinned pip versions in the standard-mode client image and the MuJoCo image; one digest-pinned client image.
3. The results pipeline publishes to the results site, and applies the token budget after the run for runs without the
   usage gateway (with it, the budget is enforced during the run, §5).
4. Solvability: tasks whose `oracle_evidence` is "none known" and the DexToolBench `partial` pairs have no verified
   positive example; until they get one, results report them separately from the tasks with a verified solution.
5. ~~Agent egress~~ done (2026-10-10 / 2026-10-11): every task on the allowlist with the honour rule (§2.11).
6. ~~Resource limits~~ done (2026-10-10, v1.2-rc): limits, caps, the monitor and the verifier step in every task,
   enforcement off by default (§2.10).
7. ~~Time cutoffs~~ done (2026-10-11 / 2026-10-12): the closing `## Time limit` in every instruction (§2.12).
8. ~~The agent's clock~~ done (2026-10-13): every standard service counts `time_left_s` from the agent's first request.

Decided (2026-10-02):
1. Success semantics stay benchmark-defined: each benchmark keeps its upstream's own rule (final state, first success,
   episode return, goal count), stated in its instructions and `docs/benchmarks/<bench>.md`.
2. Not yet implemented — standard-mode double check: the verifier replays the recorded `trajectory.npz` once more in its
   own sandbox; the sidecar's verdict stays authoritative, and a disagreement is a warning (`replay_mismatch`).
3. What each benchmark exposes to the agent in privileged mode is its own (no hiding of reward or success checks).
   Seeds: §2.13.
