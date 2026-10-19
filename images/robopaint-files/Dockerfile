# eai-robopaint-files: the RoboPaint tooling and graders every task's images use, the only copy (source
# embodied_first_exam/benchmarks/robopaint/): the agent image (privileged environment/Dockerfile) takes rcb_brush.py, the verifier images
# (tests/Dockerfile) take the graders' rcb_brush.py, rcb_brush_score.py, rcb_brush_strict.py and grade.py (privileged/ or
# standard/), with COPY --from=<this image@digest> (scripts/files_image.py; FILES.json pins it). Files only, nothing runs
# from it. Public, like its base image eai-robopaint. Build with `python3 scripts/files_image.py build robopaint-files`
# (stages context/: the files with their checkout modes and content-derived mtimes), push, then `pin` the pushed digest.
FROM scratch
COPY . /
