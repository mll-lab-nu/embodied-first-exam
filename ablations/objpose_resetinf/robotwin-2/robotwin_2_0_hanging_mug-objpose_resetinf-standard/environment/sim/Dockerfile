# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:robotwin-0.1.2
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.0-stateq@sha256:07fbf9e22ea11efd3398ef74d888ee7544410c1e07ff49e3fc5b8606b9acfe38 /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:robotwin-2-files-0.3.0-stateq@sha256:5989a990e683d2310ebe7f3020dbc68108386d4e8969688200b6373062d25b2d \
     /sim/rcb_live.py \
     /sim/server.py \
     /srv/
