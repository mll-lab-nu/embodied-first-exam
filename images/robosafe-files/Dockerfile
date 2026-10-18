# eai-robosafe-files: RoboSafeBench's task files that many rsb-* tasks share outside environment/sim/ (the paused
# standard client, the graders, the privileged tooling and scrub), at /<layer>/<file>; their one source is
# embodied_first_exam/benchmarks/robosafebench/<layer>/ (scripts/robosafe/check_release.py LAYERS). The tasks' environment/Dockerfile and
# tests/Dockerfile take them with COPY --from=<this image@digest> (scripts/files_image.py; FILES.json pins it). Files
# only, nothing runs from it. BUILD_ONLY (private). Build with `python3 scripts/files_image.py build robosafe-files`
# (stages context/: the files with their checkout modes and content-derived mtimes), push, then `pin` the pushed digest.
FROM scratch
COPY . /
