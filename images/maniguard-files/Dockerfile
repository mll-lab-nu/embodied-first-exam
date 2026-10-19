# efe-maniguard-files:0.1.0: the files maniguard's task dirs share (one copy; source
# embodied_first_exam/benchmarks/maniguard/, scripts/files_image.py; FILES.json pins it). The tasks' Dockerfiles
# take each file with COPY --from=<this image@digest> to the path a copy in the task dir had. Files only.
FROM scratch
COPY . /
