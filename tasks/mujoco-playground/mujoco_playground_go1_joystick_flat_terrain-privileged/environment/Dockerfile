# MuJoCo Playground quadruped task (privileged): plain MuJoCo with Playground's and Menagerie's assets
# (images/mujoco/prepare_assets.sh), the task's tooling and its frozen instance.
FROM ghcr.io/mll-lab-nu/efe:mujoco-0.1.3
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:mujoco-playground-files-0.7.0@sha256:347e83daa4047f377fc94b83537d406fa4c5c6c79b6b18367aba47ccd652659b /privileged/environment/rcb_quadruped.py /opt/tools/rcb_quadruped.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
