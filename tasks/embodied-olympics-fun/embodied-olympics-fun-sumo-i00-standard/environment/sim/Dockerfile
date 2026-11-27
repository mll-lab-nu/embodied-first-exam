# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.8.0@sha256:2586f42b2d63892c9a09bf77320a404d49c24171fd6a999a6672a25074843cf7 /rfo/tasks/sumo.py /srv/rfo_task.py
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:497a2b864b3a1aaf1f60206dc14f08a0f99960037f0e54be3d4bc2e39f5adba4 /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.8.0@sha256:2586f42b2d63892c9a09bf77320a404d49c24171fd6a999a6672a25074843cf7 \
     /rcb_rfo.py \
     /standard/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:497a2b864b3a1aaf1f60206dc14f08a0f99960037f0e54be3d4bc2e39f5adba4 /sidecar/rcb_service.py /srv/rcb_service.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.8.0@sha256:2586f42b2d63892c9a09bf77320a404d49c24171fd6a999a6672a25074843cf7 \
     /rfo/__init__.py \
     /rfo/looks.py \
     /rfo/realhand.py \
     /rfo/referee.py \
     /rfo/scene.py \
     /rfo/task.py \
     /rfo/world.py \
     /srv/rfo/
