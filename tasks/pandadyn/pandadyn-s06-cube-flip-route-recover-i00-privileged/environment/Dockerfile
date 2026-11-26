# Base image = ManiSkill 3.0.1 / SAPIEN 3.0.3 + the Panda Dynamic Scenes environment package (see images/pandadyn/).
# Everything task-specific is copied here; no reference controller or recorded rollout is in the image.
FROM ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:pandadyn-files-0.6.0@sha256:7eb2cefbf55ba592819cacfb25056ff48f9dff954428efdbc2623a9f2d7ab2d5 /privileged/environment/rcb_pandadyn.py /opt/tools/rcb_pandadyn.py
ENV PYTHONPATH=/opt/tools:/opt/pandadyn
# OPENBLAS_CORETYPE: this task's start depends on the BLAS kernel (tasks/pandadyn/README.md "Determinism")
ENV OPENBLAS_CORETYPE=Haswell
RUN mkdir -p /app/output
WORKDIR /app
