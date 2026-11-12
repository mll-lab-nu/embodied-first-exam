# Base image = plain MuJoCo 3.14.0 and the IKEA scenes (images/ikea-mujoco/). Everything task-specific is copied here.
FROM ghcr.io/mll-lab-nu/efe:ikea-mujoco-0.3.0
COPY --from=ghcr.io/mll-lab-nu/efe:ikea-mujoco-files-0.4.3@sha256:e5503dbe418ce54393e82a4079e4bbfe741a6793ac4a4319582ab6063fb03f3b /privileged/environment/rcb_ikea.py /opt/tools/rcb_ikea.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
