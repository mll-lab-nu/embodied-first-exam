# Base image = ManiSkill 3.0.1 / SAPIEN 3.0.3 + the Panda Dynamic Scenes environment package (see images/pandadyn/).
# Everything task-specific is copied here; no reference controller or recorded rollout is in the image.
FROM ghcr.io/mll-lab-nu/efe:pandadyn-0.1.0
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:pandadyn-files-0.2.0@sha256:92778bffefb255a07500b568d8d686a0a80258220538efd2653ffb24216fb8d1 /privileged/environment/rcb_pandadyn.py /opt/tools/rcb_pandadyn.py
ENV PYTHONPATH=/opt/tools:/opt/pandadyn
RUN mkdir -p /app/output
WORKDIR /app
