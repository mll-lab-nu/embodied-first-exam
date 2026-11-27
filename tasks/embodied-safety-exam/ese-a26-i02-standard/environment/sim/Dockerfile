# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:ese-0.5.6
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:ese-files-0.9.0@sha256:b18e2145ff869d0eba405ea1a9b06c0b41889a73ce256f05f1fecc26f725fcc0 \
     /standard/candidate_identity.py \
     /standard/picture_delivery.py \
     /standard/rcb_ese.py \
     /standard/rcb_service.py \
     /standard/replay.py \
     /standard/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.7.0@sha256:1ab8c16d4372a0b44f5c0ea7f819f6febafcfdc132013b1736a04f360375b28f /rcb1.py /srv/rcb1.py
