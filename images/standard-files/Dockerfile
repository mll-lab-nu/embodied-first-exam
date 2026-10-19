# efe-standard-files:0.1.0: the standard-mode client layer (rcb_client.py, rcb1.py of every eai-standard
# version) that standard tasks' agent images take (one copy; source embodied_first_exam/standard/,
# scripts/files_image.py; FILES.json pins it). The tasks' Dockerfiles COPY --from=<this image@digest> each file to
# the path a copy in the task dir had. Files only. Public.
FROM scratch
COPY . /
