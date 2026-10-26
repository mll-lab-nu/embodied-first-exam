# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.0@sha256:90253c4cb419668f84c6728dc6d6e23ea55ef8d7f7e7835a5eb65015729f91b0 /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.4.0@sha256:e30e534e410bb5aa8820d0585348d96cab0551c2215d2835066d69d8558ff939 \
     /rcb_rfo.py \
     /standard/rcb_service.py \
     /standard/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.4.0@sha256:e30e534e410bb5aa8820d0585348d96cab0551c2215d2835066d69d8558ff939 \
     /rfo/__init__.py \
     /rfo/looks.py \
     /rfo/realhand.py \
     /rfo/referee.py \
     /rfo/scene.py \
     /rfo/task.py \
     /rfo/world.py \
     /srv/rfo/
