# embodied_first_exam/: the code tasks share

- `benchmarks/<benchmark>/`: one folder per benchmark, the same folder name as its task dirs' `tasks/<benchmark>/`
  (`scripts/task_conventions.py` `BENCHMARK_TABLE`, e.g. `behavior-1k`, `embodied-safety-exam`, `embodied-olympics-fun`). It holds
  the single source of what many of the benchmark's task dirs would otherwise each carry a copy of: the tooling the
  agent imports (`rcb_<benchmark>.py` and its helpers), the graders, the simulator service's adapter and shared assets.
  What is specific to one task (its frozen instance, reference solution, texts, Dockerfiles, compose file) stays in
  `tasks/<benchmark>/<task>/`.
- `standard/`: the standard-mode client and service layers (docs/protocol/standard_mode.md). Tasks do not carry copies
  of them: their Dockerfiles take the files from the files-only image `standard-files` (`images/standard-files/`).
  - the top level: the shared layer (`rcb_limited.py`, `rcb_client.py`, `rcb1.py`, `run.sh`) and its tests;
  - `sidecar/`: the sidecar client and the standard grader most sidecar and realtime tasks share;
    `sidecar/clients/<name>/`: the clients some benchmarks use (`robocasa`, `kinder`, `compact`);
  - `operations/`: the operations layer (`rcb_limited.py`, `rcb_client.py`, `selftest.py`);
  - `realtime/`: the realtime layer (`rcb_realtime.py`, its client);
  - `agent_end/`: the agent-ended episode layer of the shared and the operations layers (`rcb_agent_end.py`, files-only image `agent-end-files`)
    and the tests of agent-ended episodes on every layer;
  - `mcp/`: the `efe-robot` MCP server that offers each standard and realtime task's robot service as tools, and
    `inject.py`, which `normalize` uses to write it into each task.

A task's build gets a benchmark's files from a pinned files-only image built from its folder (`scripts/files_image.py`,
`images/<name>/FILES.json`): its Dockerfiles `COPY --from=<image@digest>` each file to the same container path a copy in
the task dir would have had, so `tasks/` stays a set of self-contained Harbor task dirs. A change here needs a new image
version (`files_image.py build`, push, `pin`).

This folder is optional: the recommended place for what several tasks share is the benchmark's base image
(`images/<name>/`), so the tasks get it from the image (docs/protocol/README.md §1, "What a contribution delivers").
Code that builds or generates tasks is not kept in this repository.
