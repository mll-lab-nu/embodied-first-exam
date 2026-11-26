# MuJoCo Playground quadruped task (privileged): plain MuJoCo with Playground's and Menagerie's assets
# (images/mujoco/prepare_assets.sh), the task's tooling and its frozen instance.
FROM ghcr.io/mll-lab-nu/efe:mujoco-0.1.3
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:mujoco-playground-files-0.7.0@sha256:931d2b59ff197790ac2d917f047334a485f1ae272753ab4ba5de7612aa7edf6d /privileged/environment/rcb_quadruped.py /opt/tools/rcb_quadruped.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
