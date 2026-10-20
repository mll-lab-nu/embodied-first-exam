# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:pandadyn-0.1.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-sim-files-0.1.1@sha256:d9a4e130a67056d0fb47594562ac303b2f000c5f48fbe5ec235593bef0f3543f \
     /rcb1.py \
     /realtime/rcb_realtime.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:pandadyn-sim-files-0.1.1@sha256:37ec3c93b816b464dc58c7daa1a22a72c22ca7a09687122124496358dabb9ef6 \
     /privileged/environment/rcb_pandadyn.py \
     /sim/rcb_service.py \
     /sim/variants/727bef3b2d/server.py \
     /srv/
