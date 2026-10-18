# eai-robolab-files: RoboLab's tooling module rcb_robolab.py (source embodied_first_exam/benchmarks/robolab/), the only copy the RoboLab
# privileged tasks' images use: their environment/Dockerfile (agent, /opt/tools/rcb_robolab.py) and tests/Dockerfile
# (verifier, /tests/rcb_robolab.py) take it with COPY --from=<this image@digest> (scripts/files_image.py; FILES.json pins
# it). Files only, nothing runs from it. BUILD_ONLY (private, like eai-robolab). Build with
# `python3 scripts/files_image.py build robolab-files` (stages context/: the files with their checkout modes and
# content-derived mtimes), push, then `pin` the pushed digest.
FROM scratch
COPY . /
