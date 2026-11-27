# The `sim` sidecar's image (environment/docker-compose.yaml builds it): the base image (the simulator and the
# benchmark's 2.2 adapter at /opt/abc-tools), this directory at /srv (the frozen instance and the task's text), and
# the shared 2.2 layer from the pinned files-only image. .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:abc-sim-0.4.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.6.0@sha256:5e5e605d9f3cc2a4a0efc4ffb1f277278f8f77f225cc6ff60d00d15b4cb3b515 \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:agent-end-files-0.3.0@sha256:06f4caf4617d33158edc8ccb7b4ac5dfc607da5e1d51776ec16d0bd2d72b00ff /rcb_agent_end.py /srv/rcb_agent_end.py
