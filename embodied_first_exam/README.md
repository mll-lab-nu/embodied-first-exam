# embodied_first_exam/: the code tasks share

- `benchmarks/<benchmark>/`: one folder per benchmark, the same folder name as its task dirs' `tasks/<benchmark>/`
  (`scripts/task_conventions.py` `BENCHMARK_DIRS`, e.g. `behavior-1k`, `robosafebench`, `roboolympics-fun`). It holds
  the single source of what many of the benchmark's task dirs would otherwise each carry a copy of: the tooling the
  agent imports (`rcb_<benchmark>.py` and its helpers), the graders, the simulator service's adapter and shared assets.
  What is specific to one task (its frozen instance, reference solution, texts, Dockerfiles, compose file) stays in
  `tasks/<benchmark>/<task>/`.
- `standard/`: the standard-mode client and service layers every benchmark's standard tasks copy unchanged
  (eai-standard/2.2 at the top, `v2_4/`, the realtime layer in `realtime/`; docs/protocol/standard_mode.md).

A task's build gets a benchmark's files from a pinned files-only image built from its folder (`scripts/files_image.py`,
`images/<name>/FILES.json`): its Dockerfiles `COPY --from=<image@digest>` each file to the same container path a copy in
the task dir would have had, so `tasks/` stays a set of self-contained Harbor task dirs. A change here needs a new image
version (`files_image.py build`, push, `pin`).

This folder is optional: the recommended place for what several tasks share is the benchmark's base image
(`images/<name>/`), so the tasks get it from the image (docs/protocol/README.md §1, "What a contribution delivers").
Code that builds or generates tasks is not kept in this repository.
