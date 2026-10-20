# Base image = ManiSkill 3.0.1 / SAPIEN 3.0.3 + the Panda Dynamic Scenes environment package (see images/pandadyn/).
# Everything task-specific is copied here; no reference controller or recorded rollout is in the image.
FROM ghcr.io/mll-lab-nu/efe:pandadyn-0.1.0
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:pandadyn-files-0.1.1@sha256:4d9d1bbfff497a8ac8c83d7594b216babe8bcf68f1ca899aec471073fde7fda7 /privileged/environment/rcb_pandadyn.py /opt/tools/rcb_pandadyn.py
ENV PYTHONPATH=/opt/tools:/opt/pandadyn
# OPENBLAS_CORETYPE: this task's start depends on the BLAS kernel (tasks/pandadyn/README.md "Determinism")
ENV OPENBLAS_CORETYPE=Haswell
RUN mkdir -p /app/output
WORKDIR /app
