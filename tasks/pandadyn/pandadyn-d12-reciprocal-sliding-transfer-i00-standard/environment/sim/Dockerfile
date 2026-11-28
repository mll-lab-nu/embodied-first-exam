# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.9.0@sha256:2cf5b6f826d698eaa0dcddf1561e6c673ca0ddabac2c3868d823598eb3cb75b6 /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:pandadyn-files-0.8.0@sha256:4ef22683df701991d883767a61bc30c2aee31bab58da90ffd47db9a97f15161e \
     /privileged/environment/rcb_pandadyn.py \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.9.0@sha256:2cf5b6f826d698eaa0dcddf1561e6c673ca0ddabac2c3868d823598eb3cb75b6 /sidecar/rcb_service.py /srv/rcb_service.py
