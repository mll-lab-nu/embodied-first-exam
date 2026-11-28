# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.8.0@sha256:1149811a2c2d62a41af39e58acd2bd9e490459a5124d1435752b59212ec5d164 /rfo/tasks/first_time_shot.py /srv/rfo_task.py
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:ba111a75bfe7b63b7119f1699fe0d61e565ad6cd4d504591e32fdea7c826c795 /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.8.0@sha256:1149811a2c2d62a41af39e58acd2bd9e490459a5124d1435752b59212ec5d164 \
     /rcb_rfo.py \
     /standard/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:ba111a75bfe7b63b7119f1699fe0d61e565ad6cd4d504591e32fdea7c826c795 /sidecar/rcb_service.py /srv/rcb_service.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.8.0@sha256:1149811a2c2d62a41af39e58acd2bd9e490459a5124d1435752b59212ec5d164 \
     /rfo/__init__.py \
     /rfo/looks.py \
     /rfo/realhand.py \
     /rfo/referee.py \
     /rfo/scene.py \
     /rfo/task.py \
     /rfo/world.py \
     /srv/rfo/
