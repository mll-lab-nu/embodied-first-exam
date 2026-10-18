# embodied_first_exam/: the code a benchmark's tasks share

One folder per benchmark, `embodied_first_exam/benchmarks/<benchmark>/`: the same folder name as its task dirs' `tasks/<benchmark>/`
(`scripts/task_conventions.py` `BENCHMARK_DIRS`, e.g. `behavior-1k`, `robosafebench`, `roboolympics-fun`). It holds the single source of what many of the benchmark's task dirs would
otherwise each carry a copy of: the tooling the agent imports (`rcb_<benchmark>.py` and its helpers), the graders, the
simulator service's adapter and shared assets. What is specific to one task (its frozen instance, reference solution,
texts, Dockerfiles, compose file) stays in `tasks/<benchmark>/<task>/`.

A task's build gets these files from a pinned files-only image built from the folder (`scripts/files_image.py`,
`images/<name>/FILES.json`): its Dockerfiles `COPY --from=<image@digest>` each file to the same container path a copy in
the task dir would have had, so `tasks/` stays a set of self-contained Harbor task dirs. A change here needs a new image
version (`files_image.py build`, push, `pin`); the benchmark's generator check fails until the image matches.

The generators stay under `scripts/<benchmark>/`. Code several benchmarks share (the resource monitor, the
eai-standard layer) stays in `scripts/rcb_monitor/` and `scripts/eai_standard/`.
