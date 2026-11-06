# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:bigym2-0.1.1
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.1@sha256:7f1a830075fd6dd25e7a20a340316c041df583a29062796f59a4fa63b6f76946 /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:bigym2-files-0.4.0@sha256:fe8dd55600b32447391fbe16e1789a0df479ac6a17190ecf2f85cd59af9a5447 \
     /privileged/environment/rcb_bigym2.py \
     /sim/rcb_service.py \
     /sim/server.py \
     /srv/
