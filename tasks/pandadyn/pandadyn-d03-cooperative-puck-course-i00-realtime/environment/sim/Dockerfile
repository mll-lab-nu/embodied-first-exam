# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.0@sha256:90253c4cb419668f84c6728dc6d6e23ea55ef8d7f7e7835a5eb65015729f91b0 \
     /rcb1.py \
     /realtime/rcb_realtime.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:pandadyn-files-0.4.0@sha256:1fa728bd3b4ce80213fc0f2613f97bbbb51f31a5c5b5aa9ed9aa8582a61fa1e1 \
     /privileged/environment/rcb_pandadyn.py \
     /sim/rcb_service.py \
     /sim/variants/727bef3b2d/server.py \
     /srv/
