# eai-control-transfer-anycar-files: AnyCar's two track data files (F1DB circuits, compact routes; licences in
# embodied_first_exam/benchmarks/roboengineer/anycarbench/), the only copy the roboEngineer AnyCar tasks' agent images use:
# their environment/Dockerfile takes them with COPY --from=<this image@digest> (scripts/files_image.py; FILES.json pins
# it). Files only, nothing runs from it. BUILD_ONLY (private). Build with
# `python3 scripts/files_image.py build control-transfer-anycar-files` (stages context/: the files with their checkout
# modes and content-derived mtimes), push, then `pin` the pushed digest.
FROM scratch
COPY . /
