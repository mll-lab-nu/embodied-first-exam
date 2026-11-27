# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.7.0@sha256:127ba76f98a0ad602b378f1aff38c5defe668e74d46f637e3d0fdf26adf6bbef /rfo/tasks/volleyball_set.py /srv/rfo_task.py
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.6.0@sha256:a5fa8a9d299f6027a84f45af38a297139ad8cf68231a911272064ee9c1edbb13 /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.7.0@sha256:127ba76f98a0ad602b378f1aff38c5defe668e74d46f637e3d0fdf26adf6bbef \
     /rcb_rfo.py \
     /standard/rcb_service.py \
     /standard/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.7.0@sha256:127ba76f98a0ad602b378f1aff38c5defe668e74d46f637e3d0fdf26adf6bbef \
     /rfo/__init__.py \
     /rfo/looks.py \
     /rfo/realhand.py \
     /rfo/referee.py \
     /rfo/scene.py \
     /rfo/task.py \
     /rfo/world.py \
     /srv/rfo/
