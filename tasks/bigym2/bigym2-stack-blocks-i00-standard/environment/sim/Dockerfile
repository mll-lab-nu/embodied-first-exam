# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:bigym2-0.1.1
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.1@sha256:7f1a830075fd6dd25e7a20a340316c041df583a29062796f59a4fa63b6f76946 /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:bigym2-files-0.4.1@sha256:7f7725261d7a32d4bb178738cb55ed6869d732385f2f04cab75c7b86e9e0a616 \
     /privileged/environment/rcb_bigym2.py \
     /sim/rcb_service.py \
     /sim/server.py \
     /srv/
