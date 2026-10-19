# Base image = plain MuJoCo 3.14.0 and the IKEA scenes (images/ikea-mujoco/). Everything task-specific is copied here.
FROM ghcr.io/mll-lab-nu/efe-private:ikea-mujoco-0.3.0
COPY --from=ghcr.io/mll-lab-nu/efe-private:ikea-mujoco-files-0.1.0@sha256:bf7494f261723da1ef81fb4a6314a8daba4a5a2a5373ce787652ada708314af0 /privileged/environment/rcb_ikea.py /opt/tools/rcb_ikea.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
