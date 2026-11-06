# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:libero-max-0.1.1
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:libero-max-files-0.4.1@sha256:2e9e6f1c7bb3835523d2b6694aaaabb052fee0683abe81e1bf530918428cab11 \
     /sim/finalize.sh \
     /privileged/environment/lmx_tool.py \
     /sim/rcb_service.py \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.0@sha256:90253c4cb419668f84c6728dc6d6e23ea55ef8d7f7e7835a5eb65015729f91b0 /rcb1.py /srv/rcb1.py
