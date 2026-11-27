# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:kinder-0.1.6
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.6.0@sha256:a5fa8a9d299f6027a84f45af38a297139ad8cf68231a911272064ee9c1edbb13 /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:kinder-files-0.6.0@sha256:0d39f957778e7f3fd5e818b29c68c7c268f86e94c14bc37da37fc253d1f596f5 \
     /privileged/environment/rcb_kinder.py \
     /sim/rcb_service.py \
     /sim/server.py \
     /srv/
