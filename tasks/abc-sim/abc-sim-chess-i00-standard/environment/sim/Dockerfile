# The `sim` sidecar's image (environment/docker-compose.yaml builds it): the base image (the simulator and the
# benchmark's 2.2 adapter at /opt/abc-tools), this directory at /srv (the frozen instance and the task's text), and
# the shared 2.2 layer from the pinned files-only image. .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:abc-sim-0.5.1
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.6.0@sha256:a5fa8a9d299f6027a84f45af38a297139ad8cf68231a911272064ee9c1edbb13 \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:agent-end-files-0.3.0@sha256:0552248dc25d140cdef331d0b6a6e46b10d7ee3f1ef6053fbf0c51ba5e9e3a92 /rcb_agent_end.py /srv/rcb_agent_end.py
