# The `sim` sidecar's image (environment/docker-compose.yaml builds it): the base image (the simulator and the
# benchmark's realtime adapter at /opt/abc-tools), this directory at /srv (the frozen instance and the task's text), and
# the shared realtime layer from the pinned files-only image. .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:abc-sim-0.6.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:a99b04e29e96564b62a2c335b191405d8a94785d6efea2bb5765acbefde92383 \
     /rcb1.py \
     /realtime/rcb_realtime.py \
     /srv/
