# Invariants

These eight invariants keep results honest: no reward without solving the task, one verdict for one deliverable, and
results compared only with comparable results. Each holds for every task in every mode, including tasks a benchmark
exports with its own runtime. No task value, declaration or benchmark document can override them. The one setting
left to a task's author is the agent's network: the allowlist, unless the task declares open egress (H.6).

**How CI holds them.** The required job `invariants` (`ci_checks/run_invariants.sh`) runs exactly the checks named
below. It fails on any failure, error or incomplete run. `ci_checks/check-ci-selftest.py --tier invariants` breaks
real tasks in each way and requires the checks to fail. What CI cannot see (images, live endpoints, the runner) is
held by the reviewer and the runner.

## H.1 Verifier isolation

- The verifier runs in a sandbox of its own: `[verifier] environment_mode = "separate"`, an image built from `tests/`,
  and `tests/Dockerfile` ships `test.sh`.
- It receives only the declared artifacts. In the standard modes it transcribes the sidecar's verdict (H.4).
- `tests/test.sh` first empties `/logs/verifier`. Before anything reads the agent's files, it removes from
  `/app/output` whatever is not the agent's own regular file or directory (links out of it, FIFOs, devices). Reward
  files are written fresh.
- No writable volume crosses the trust boundary. A named volume mounted by a trusted container (the verifier, a
  sidecar) is named `*_trusted` and is never mounted by the agent's container.
- The agent's container binds no task file, host path or socket. The one exception is a directory the runner names
  as a whole `${RCB_*}` variable.
- No service widens its container (`privileged`, `cap_add`, `devices`, host namespaces, `volumes_from`, OOM
  settings). No service takes files by another road (`secrets`, `configs`, `env_file`, `build`, `include`) or sets
  its own network. Sidecars publish no port.
- The resource monitor is the one service exempt from these rules. It has no network and runs its code from a pinned
  image. It mounts its caps (`limits.json`) read-only. It is the only writer of the beacons, which are read-only
  everywhere else. It seals its record in the first sidecar collect hook.
- Code a verifier runs for the agent (a `policy` deliverable) runs as an unprivileged user in its own process,
  without network and under a process limit. It cannot read the simulator, the evaluator or the requests. Every
  process it started ends before anything is graded. It cannot write the logs or the report the grade is read from.
- A new benchmark merges only after one adversarial trial scored 0 on its tasks. That trial's agent is told to obtain
  reward without solving the task.

*CI:* `check-verifier-isolation.sh`, `check-monitor.py --tier invariants`, the benchmarks' `invariant-*` hooks;
review.

## H.2 No answer in reach

- Reference solutions exist only under `solution/`, which is mounted for the oracle agent only.
- Nothing the agent's container can read contains a solution of the task or a pointer to one. That covers the task's
  `environment/` files, the task and base images, the tooling, the frozen instance and installed documentation. A
  pointer is a URL, a dataset or file name, a demonstration or episode id, or the name of the upstream expert or
  policy for this task.
- Upstream experts, recorded demonstrations and policies trained for the task are scrubbed from images. Provenance
  lives in the task README and `tasks/<benchmark>/README.md`.

*CI:* `check-agent-pointers.py`, each benchmark's `ci_checks/benchmarks/<bench>/invariant-*` hooks. Images are
reviewed when built ([leakage.md](leakage.md)).

## H.3 Standard trust boundary

This invariant covers the standard and realtime modes.

- The simulator, the scene, the frozen instance, the seed and the success predicate run in the `sim` sidecar.
- The agent's image holds no simulator or simulation code. `environment/Dockerfile` copies nothing from `sim/`, and
  uses no `.` or wildcard source.
- The agent reaches the service only through the protocol's endpoints. Every other path is a 404 (no `/state`, no
  `/success`).
- The service exposes no object poses, scene files, seed, success predicate or its parameters beyond what the
  instruction states. It exposes no segmentation and no contact forces on objects. The exception is telemetry that
  the benchmark's README declares field by field, and that never gives an object's pose.
- The service never shows the task's success or progress toward it. Every standard and realtime task served by an
  `eai-standard` service has agent-ended episodes ([eai-standard.md](eai-standard.md#agent-ended-episodes)): no
  answer depends on the success, and the agent ends the episode.
- The agent's controller runs in the agent's own container. No agent code runs next to the simulator.

*CI:* `check-standard-agent-image.sh`, `check-verifier-isolation.sh` (topology, ports),
`check-agent-end.py --tier invariants`; the service's own `/spec` checks; review.

## H.4 Trusted verdict

- The verdict comes only from a trusted source.
- Privileged mode: a replay, in a fresh process in the verifier, of the agent's deliverable from the frozen initial
  state.
- Standard and realtime modes: the sim sidecar's record of the live episode (`final.json`, its `success`). The
  service judges the episode it ran, from a frozen initial state it checked when the episode began and after every
  reset. The verifier transcribes the record. No replay decides it, and nothing the verifier renders afterwards (a
  video) does.
- What keeps that record trusted:
  - the agent cannot write the sidecar's state: its volumes are `*_trusted` and it publishes no port;
  - the evidence is collected only from the sidecar;
  - when the agent's time is up, the collect hooks stop every process the agent left running (`kill -9 -1` in its
    container) before the sidecar is signalled. Only the resource monitor's seal comes first;
  - from that signal on, the service refuses every request that would run the simulator, a settle or hold window
    included. The sidecar finalizes an episode the agent can no longer change;
  - the sidecar keeps the episode's journal or trajectory as the deliverable.
- Nothing the agent's container writes decides the verdict, except the privileged deliverable that is replayed.
- The verifier uses no network.
- A verdict once written in a trial is never rewritten. A later re-grade keeps the original beside it.
- The frozen instance the verifier or the sidecar grades against and the one the trial ran from are byte-identical
  copies.

*CI:* `check-verifier-isolation.sh` (evidence and collect hook from a sidecar), `check-instance-copies.sh`.

## H.5 Infrastructure rerun

- An attempt that failed for infrastructure reasons is void. It needs positive evidence: a model API or account
  error, a usage limit, a host or launch that died, or the verifier's `infra_error` / `grader_error`.
- A void attempt is moved aside and never counted. The task may be rerun with the same instance, seed and
  configuration, with all agent and environment state cleared, until an attempt gives a result.
- A graded failure is a result and is never rerun: the agent's 0, its cutoff, its token budget, its own exit. A
  success is never rerun either.
- The rule is the runner's: `scripts/retry_policy.py` ([running.md](running.md#infrastructure-failures-rerun)).

*CI:* `scripts/tests/test_retry_policy.py`, `scripts/tests/test_runner_results.py`.

## H.6 Egress

- During the agent phase, the agent's container and every service in its network namespace reach only the allowlist,
  `HOSTS` in `scripts/set_agent_egress.py`: the model APIs and the package registries.
- In `task.toml` this is `[agent] network_mode = "allowlist"` with exactly those hosts, and no step with a policy of
  its own. An official run narrows it further to the usage gateway and the registries.
- The task's author may instead declare open egress: `[agent] network_mode = "public"`, with no host list. The runner
  applies what the task declares. Open-network results are ranked apart.
- The verifier has no network. Every task has `[verifier] network_mode = "no-network"` (written by `normalize`). No
  service of `tests/docker-compose.yaml` has a network setting other than `none`.

*CI:* `check-verifier-isolation.sh`.

## H.7 Comparable modes

- Where a task is offered both in privileged mode and in a standard mode, the two share one frozen instance
  (byte-identical copies), one success rule and the same seeds (`instance_seed`, and `[metadata.seeds]` `allowed` and
  `build`).
- A standard-mode task has the same cutoff as the same task in privileged mode (`same_cutoff_as` in the mode
  registry).
- One success rule is not one length rule. Where the privileged deliverable has an action or time limit the standard
  task does not, `tasks/<benchmark>/README.md` states both. Read cross-mode comparisons of those tasks with that in
  mind.

*CI:* `check-twins.py`, `check-instance-copies.sh`.

## H.8 DIGEST

- `tasks/<benchmark>/<task>/DIGEST` is the digest Harbor publishes the task under: `sha256:<hex>` over the relative
  path and content hash of `task.toml`, `instruction.md`, `README.md` and every file under `environment/`, `tests/`
  and `solution/`.
- `normalize` writes it last, and it equals the digest of the task's current files.
- Results are attributed to a task by its digest. A changed file is a changed task.

*CI:* `check-dataset-manifest.sh`.
