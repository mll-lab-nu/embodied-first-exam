# The `sim` sidecar's image (environment/docker-compose.yaml builds it): the base image (the simulator and the
# benchmark's 2.2 adapter at /opt/abc-tools), this directory at /srv (the frozen instance and the task's text), and
# the shared 2.2 layer from the pinned files-only image. .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:abc-sim-0.4.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.5.0@sha256:d0f4045938a9683719f71de2342464216b53c49a87711923fb4afd551c081d82 \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:agent-end-files-0.2.0@sha256:85bb0e3d2a49a8c94d1cefa47d8556d96b9d4afa528fd5ea9532cf53cb79a6e6 /rcb_agent_end.py /srv/rcb_agent_end.py
