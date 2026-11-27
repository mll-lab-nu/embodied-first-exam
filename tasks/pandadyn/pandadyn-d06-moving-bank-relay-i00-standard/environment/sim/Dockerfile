# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.6.0@sha256:a5fa8a9d299f6027a84f45af38a297139ad8cf68231a911272064ee9c1edbb13 /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:pandadyn-files-0.7.0@sha256:85864153ee01c45b489fd7cfe6443e467c19cd5e03104c64e9519767f3a29350 \
     /privileged/environment/rcb_pandadyn.py \
     /sim/rcb_service.py \
     /sim/server.py \
     /srv/
