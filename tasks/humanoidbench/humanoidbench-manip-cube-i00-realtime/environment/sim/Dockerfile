# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:humanoidbench-0.2.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.0@sha256:90253c4cb419668f84c6728dc6d6e23ea55ef8d7f7e7835a5eb65015729f91b0 \
     /rcb1.py \
     /realtime/rcb_realtime.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:humanoidbench-files-0.4.0@sha256:ce4fd00e84bb202de450b54de645a1bdb35b19767d0e07de298c329072632528 \
     /privileged/environment/rcb_hb.py \
     /privileged/tests/rcb_rewards.py \
     /sim/rcb_service.py \
     /sim/server.py \
     /srv/
