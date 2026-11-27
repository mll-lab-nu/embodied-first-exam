# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:robotwin-0.1.2
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.6.0@sha256:a5fa8a9d299f6027a84f45af38a297139ad8cf68231a911272064ee9c1edbb13 /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:robotwin-2-files-0.5.0@sha256:d88a3788d768df728991183a51f820c1bb7eaf1fbd5eb4debb51916ecffb8c69 \
     /sim/rcb_live.py \
     /sim/server.py \
     /srv/
