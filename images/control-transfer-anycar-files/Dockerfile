# eai-control-transfer-anycar-files: AnyCar's two track data files (F1DB circuits, compact routes; licences in
# scripts/control_transfer/components/anycarbench/), the only copy the roboEngineer AnyCar tasks' agent images use:
# their environment/Dockerfile takes them with COPY --from=<this image@digest> (scripts/files_image.py; FILES.json pins
# it). Files only (FROM scratch, nothing runs from it). Not public, like the roboEngineer images. Build with
# `python3 scripts/files_image.py build control-transfer-anycar-files` (a stamped copy of the files), push, then `pin`.
FROM scratch
COPY circuits.json compact_routes.json /
