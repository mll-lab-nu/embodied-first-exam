# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:kinder-0.1.6
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-sim-files-0.1.1@sha256:d9a4e130a67056d0fb47594562ac303b2f000c5f48fbe5ec235593bef0f3543f /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:kinder-sim-files-0.1.1@sha256:94e9b8779d2fd9b856d88a138d3c42952f0985b437be6c4d3f71c853548803b4 \
     /privileged/environment/rcb_kinder.py \
     /sim/rcb_service.py \
     /sim/server.py \
     /srv/
