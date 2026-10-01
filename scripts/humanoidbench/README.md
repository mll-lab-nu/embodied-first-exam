# scripts/humanoidbench — where the HumanoidBench tasks come from

Every `tasks/humanoidbench-*` directory is generated from this one. Nothing in them is edited by hand. Agent
results are published on the results site, not kept here (PROTOCOL D3).

| file | what it is |
|---|---|
| `subset.toml` | **the source of truth.** Which of HumanoidBench's 32 task classes we ship, which capability class each belongs to, why it was kept, how to describe it to the agent, and its `status` |
| `facts.json` | the numbers the *simulator* is the authority on — success bars, action/observation widths, episode limits, the all-zero-trajectory floor. Generated; never hand-edited |
| `shared/rcb_hb.py` | the one real copy of the agent-facing tooling. Every task gets a byte copy in `environment/` and `tests/` (a standard twin: in `environment/sim/`, the sidecar's). It names **no task at all** — it reads which task and env it is out of the instance file, so one file can be identical everywhere without telling an agent that the other tasks exist |
| `shared/grade.py` | the one real copy of the privileged-mode verifier |
| `shared/rcb_rewards.py` | restores a task's reward function where the scoring happens: `tests/` (the verifier's own container) and a standard twin's `environment/sim/` (the sidecar the agent cannot open). Never where the agent works |
| `rewards.json` | the 32 reward implementations lifted from upstream, plus the constants, weights and helpers that exist only to serve them. The base image has them deleted (`images/humanoidbench/scrub_oracles.py`); `render` copies **one family's entry** into the same two places. A dense reward is the answer key — see `docs/benchmarks/humanoidbench.md` |
| `extract_rewards.py` | regenerates `rewards.json`, by running the real `scrub_oracles.py` against a copy of upstream and diffing — so what the image loses and what the verifier restores cannot drift. One-off; needs an image whose rewards are *not* scrubbed |
| `measure_baselines.py` | the `nop` / `hold` floors for all 32 upstream families, including the ones outside the subset — the evidence for which families deserve a slot |
| `templates/` | everything the tasks have in common, with `{{placeholders}}` |
| `templates/standard/`, `shared/standard/` | the same for each task's standard-mode twin (`tasks/*-standard/`, `eai-standard/2.1`): `rcb_service.py` (the simulator-agnostic service: endpoints, RCB1, episode, crash recovery, finalize), `server.py` (the HumanoidBench adapter), `rcb_client.py` and `rcb1.py` (the agent's client; its docstring is the API reference), `grade.py` (the verifier). Per-task prose is the task's `[task.standard]` table in `subset.toml` |
| `standard_probe.py` | what `measure-standard` runs against a twin's sim service: contract checks, the all-zero return against `facts.json`, a crash it must survive, the t=0 camera images, and the per-step cost the instruction quotes |
| `oracles/<family>/<mode>/` | a task's reference solution, where it has one (only the `sit_simple` fixture, both modes; files directly under `oracles/<family>/` go to both); `render` copies it to `solution/` |
| `configs/codex-openrouter.yaml` | the Harbor job config the recorded runs use: Harbor's own Codex agent on OpenRouter |
| `tests/test_standard_service.py` | the standard-mode service, client and verifier against a toy simulator (`python -m unittest discover -s scripts/humanoidbench/tests`; numpy, requests) |
| `gen_tasks.py` | the generator |

```bash
./gen_tasks.py status                # what exists and how far it is verified   (no simulator needed)
./gen_tasks.py render                # rewrite every task dir from the sources  (no simulator needed)
./gen_tasks.py check                 # tasks/ must be what render writes; no leaked formula, no task naming another
./gen_tasks.py measure               # refresh facts.json                       (needs mujoco)
./gen_tasks.py instance [--force]    # draw and freeze the scenes               (needs mujoco)
./gen_tasks.py verify                # re-measure; fail on drift, on a passing nop, on non-determinism
./gen_tasks.py measure-standard      # check + time each standard twin's sim service (needs a GPU: --gpus all)
```

## Adding a task

1. Add a `[[task]]` block to `subset.toml`, with its `[task.standard]` table and its `oracle_evidence`. Its `env_id`
   lives there and nowhere else.
2. `./gen_tasks.py measure <family> && ./gen_tasks.py instance <family>`, then `./gen_tasks.py measure-standard <family>`
   (with a GPU: `docker run --gpus all -e NVIDIA_DRIVER_CAPABILITIES=compute,graphics,utility ...`), then
   `./gen_tasks.py render <family>`
3. `./gen_tasks.py verify <family>` and `./gen_tasks.py check`, then `ci_checks/run_all.sh` and `cd tasks && harbor add --scan .`

Everything except `status` and `render` needs a simulator, and the simulator lives in the image, so run them there:

```bash
docker run --rm -v $PWD:/repo -w /repo ghcr.io/embodied-agent-interface-v2-internal/eai-humanoidbench:$(cat images/humanoidbench/VERSION) \
  python scripts/humanoidbench/gen_tasks.py verify
```

`measure` and `verify` restore the reward function from `rewards.json` first — the image has none, and a
floor measured any other way would not be the number the verifier produces.

## Changing something that every task shares

Edit `shared/` or `templates/`, then `./gen_tasks.py render`. All forty-eight directories (24 tasks, two modes)
move together — that is the whole point. `./gen_tasks.py check` fails when `tasks/` is not what `render` writes from
today's sources, so a bar in `facts.json` or a sentence in `subset.toml` cannot change without the instructions
following.

## Why the instance files are guarded

`gen_tasks.py instance` will not overwrite an existing `instance.npz` without `--force`. An instance is an
identity, not a cache: it is what the `dataset.toml` digest covers and what any recorded trajectory was
solved against. Redrawing with the same seed does reproduce it byte for byte — `Session.make_instance()`
seeds both the gymnasium RNG and the legacy global `np.random` that upstream uses for goals — so the guard
only ever catches the accidental case.

Background: `docs/benchmarks/humanoidbench.md` (why these tasks) and upstream,
[HumanoidBench](https://github.com/carlosferrazza/humanoid-bench).
