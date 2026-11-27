# The `sim` sidecar's image (environment/docker-compose.yaml builds it): the base image (the simulator and the
# benchmark's realtime adapter at /opt/abc-tools), this directory at /srv (the frozen instance and the task's text), and
# the shared realtime layer from the pinned files-only image. .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:abc-sim-0.5.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.6.0@sha256:5e5e605d9f3cc2a4a0efc4ffb1f277278f8f77f225cc6ff60d00d15b4cb3b515 \
     /rcb1.py \
     /realtime/rcb_realtime.py \
     /srv/
