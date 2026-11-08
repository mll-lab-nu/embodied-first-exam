# Base image = plain MuJoCo 3.14.0 and the IKEA scenes (images/ikea-mujoco/). Everything task-specific is copied here.
FROM ghcr.io/mll-lab-nu/efe:ikea-mujoco-0.3.0
COPY --from=ghcr.io/mll-lab-nu/efe:ikea-mujoco-files-0.4.2@sha256:0cb74965f760e756ec7ac0bb41b7b16fba27aa12bfc382425945fa0cedd2b201 /privileged/environment/rcb_ikea.py /opt/tools/rcb_ikea.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
