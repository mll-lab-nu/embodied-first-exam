# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:bigym2-0.1.1
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:ba111a75bfe7b63b7119f1699fe0d61e565ad6cd4d504591e32fdea7c826c795 /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:bigym2-files-0.8.0@sha256:eb9a1bf401624b1fb48815b67121d930028f66c4380caa441074a58e214db6b8 \
     /privileged/environment/rcb_bigym2.py \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:ba111a75bfe7b63b7119f1699fe0d61e565ad6cd4d504591e32fdea7c826c795 /sidecar/rcb_service.py /srv/rcb_service.py
