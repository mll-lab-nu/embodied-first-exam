# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:robotwin-0.1.2
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.9.0@sha256:2cf5b6f826d698eaa0dcddf1561e6c673ca0ddabac2c3868d823598eb3cb75b6 /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:robotwin-2-files-0.7.0@sha256:4311ece94d3eb7afedaa31f84bde939dafb9137b4f43fb05cce92282aba15c95 \
     /sim/rcb_live.py \
     /sim/server.py \
     /srv/
