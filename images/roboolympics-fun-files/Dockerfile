# eai-roboolympics-fun-files: the RoboOlympics-Fun tooling every privileged task and every standard verifier would
# otherwise carry a copy of (rcb_rfo.py, the rfo package's core, the privileged grader grade.py, the standard grader
# standard/grade.py), from their one source embodied_first_exam/benchmarks/roboolympics-fun/. The tasks' environment/Dockerfile and
# tests/Dockerfile take them with COPY --from=<this image@digest> (scripts/files_image.py; FILES.json pins it). Files
# only, nothing runs from it. Public, like eai-robofunolympics. Build with
# `python3 scripts/files_image.py build roboolympics-fun-files` (stages context/: the files with their checkout modes
# and content-derived mtimes), push, then `pin` the pushed digest.
FROM scratch
COPY . /
