# eai-behavior-files: the BEHAVIOR-1K tasks' shared tooling and graders (rcb_behavior.py, r1pro_primitives_eval.yaml,
# privileged/grade.py, standard/grade.py; source embodied_first_exam/benchmarks/behavior-1k/), the only copy the privileged agent images and
# both modes' verifier images use: their Dockerfiles take them with COPY --from=<this image@digest>
# (scripts/files_image.py; FILES.json pins it). Files only, nothing runs from it. BUILD_ONLY (private). Build with
# `python3 scripts/files_image.py build behavior-files` (stages context/: the files with their checkout modes and
# content-derived mtimes), push, then `pin` the pushed digest.
FROM scratch
COPY . /
