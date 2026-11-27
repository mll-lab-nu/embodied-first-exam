# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.8.0@sha256:d9c06edb0e5eb9a5c72a90fd971ae469b1758feb8a3ec76722b7f7df80013e46 /rfo/tasks/juggle_three.py /srv/rfo_task.py
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:6bf677373ff69d440d4640253caed50067929b8bf4a5d3a9c5f7315cd2752470 /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.8.0@sha256:d9c06edb0e5eb9a5c72a90fd971ae469b1758feb8a3ec76722b7f7df80013e46 \
     /rcb_rfo.py \
     /standard/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:6bf677373ff69d440d4640253caed50067929b8bf4a5d3a9c5f7315cd2752470 /sidecar/rcb_service.py /srv/rcb_service.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.8.0@sha256:d9c06edb0e5eb9a5c72a90fd971ae469b1758feb8a3ec76722b7f7df80013e46 \
     /rfo/__init__.py \
     /rfo/looks.py \
     /rfo/realhand.py \
     /rfo/referee.py \
     /rfo/scene.py \
     /rfo/task.py \
     /rfo/world.py \
     /srv/rfo/
