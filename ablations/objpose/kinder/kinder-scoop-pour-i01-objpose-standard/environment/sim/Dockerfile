# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:kinder-0.1.6
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.0-stateq@sha256:07fbf9e22ea11efd3398ef74d888ee7544410c1e07ff49e3fc5b8606b9acfe38 /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:kinder-files-0.4.0-stateq@sha256:45e8a2fcd544150607869fd9b0c9d881a5e80d86c1dc636f674b3c7c99fef021 \
     /privileged/environment/rcb_kinder.py \
     /sim/rcb_service.py \
     /sim/server.py \
     /srv/
