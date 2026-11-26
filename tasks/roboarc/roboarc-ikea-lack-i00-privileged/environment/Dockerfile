# Base image = plain MuJoCo 3.14.0 and the IKEA scenes (images/ikea-mujoco/). Everything task-specific is copied here.
FROM ghcr.io/mll-lab-nu/efe:ikea-mujoco-0.3.0
COPY --from=ghcr.io/mll-lab-nu/efe:ikea-mujoco-files-0.5.0@sha256:e0fb14a1db1ae5ddcf4096e0fac23ea76772056ac218c841e6c253dfb8c92e9e /privileged/environment/rcb_ikea.py /opt/tools/rcb_ikea.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
