# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:bigym2-0.1.1
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.5.0@sha256:a6c2ac2ede9fe2c1744f9c6e67c6a49de9c5a8b8c2c9ae4f0d774b7dd72662ff \
     /rcb1.py \
     /realtime/rcb_realtime.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:bigym2-files-0.6.0@sha256:327646472ac5cdbd2c19a0aff740ab3937158606626437b4d2090429bd3e78bf \
     /privileged/environment/rcb_bigym2.py \
     /sim/rcb_service.py \
     /sim/server.py \
     /srv/
