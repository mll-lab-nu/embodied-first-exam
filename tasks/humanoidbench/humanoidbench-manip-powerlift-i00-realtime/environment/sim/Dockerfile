# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:humanoidbench-0.2.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.7.0@sha256:1ab8c16d4372a0b44f5c0ea7f819f6febafcfdc132013b1736a04f360375b28f \
     /rcb1.py \
     /realtime/rcb_realtime.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:humanoidbench-files-0.6.0@sha256:88b881a25e2af7d50bde212c839aa50dee16117532eb19c7208db454fef9af2d \
     /privileged/environment/rcb_hb.py \
     /privileged/tests/rcb_rewards.py \
     /sim/rcb_service.py \
     /sim/server.py \
     /srv/
