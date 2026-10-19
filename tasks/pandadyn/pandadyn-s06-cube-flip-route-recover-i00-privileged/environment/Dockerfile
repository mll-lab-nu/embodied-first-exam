# Base image = ManiSkill 3.0.1 / SAPIEN 3.0.3 + the Panda Dynamic Scenes environment package (see images/pandadyn/).
# Everything task-specific is copied here; no reference controller or recorded rollout is in the image.
FROM ghcr.io/mll-lab-nu/efe:pandadyn-0.1.0
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:pandadyn-files-0.1.0@sha256:3f575ac291b2c8dd4f91cfbeb9e3ab44b69ca3d67541929a02493294bc249707 /privileged/environment/rcb_pandadyn.py /opt/tools/rcb_pandadyn.py
ENV PYTHONPATH=/opt/tools:/opt/pandadyn
# OPENBLAS_CORETYPE: this task's start depends on the BLAS kernel (docs/benchmarks/pandadyn.md "Determinism")
ENV OPENBLAS_CORETYPE=Haswell
RUN mkdir -p /app/output
WORKDIR /app
