# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.6.0@sha256:047fc6d0a319cb94faf708c29d23a277c3ee1dad33e8cdad55fdae7a1d902581 /rfo/tasks/volleyball_set.py /srv/rfo_task.py
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.5.0@sha256:a6c2ac2ede9fe2c1744f9c6e67c6a49de9c5a8b8c2c9ae4f0d774b7dd72662ff /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.6.0@sha256:047fc6d0a319cb94faf708c29d23a277c3ee1dad33e8cdad55fdae7a1d902581 \
     /rcb_rfo.py \
     /standard/rcb_service.py \
     /standard/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.6.0@sha256:047fc6d0a319cb94faf708c29d23a277c3ee1dad33e8cdad55fdae7a1d902581 \
     /rfo/__init__.py \
     /rfo/looks.py \
     /rfo/realhand.py \
     /rfo/referee.py \
     /rfo/scene.py \
     /rfo/task.py \
     /rfo/world.py \
     /srv/rfo/
