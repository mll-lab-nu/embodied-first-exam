# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.8.0@sha256:478a80323078a4307beab89e355383f89407285a81635e9adb48a154efc7b2b3 /rfo/tasks/goalkeeper_save.py /srv/rfo_task.py
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.9.0@sha256:2cf5b6f826d698eaa0dcddf1561e6c673ca0ddabac2c3868d823598eb3cb75b6 /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.8.0@sha256:478a80323078a4307beab89e355383f89407285a81635e9adb48a154efc7b2b3 \
     /rcb_rfo.py \
     /standard/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.9.0@sha256:2cf5b6f826d698eaa0dcddf1561e6c673ca0ddabac2c3868d823598eb3cb75b6 /sidecar/rcb_service.py /srv/rcb_service.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.8.0@sha256:478a80323078a4307beab89e355383f89407285a81635e9adb48a154efc7b2b3 \
     /rfo/__init__.py \
     /rfo/looks.py \
     /rfo/realhand.py \
     /rfo/referee.py \
     /rfo/scene.py \
     /rfo/task.py \
     /rfo/world.py \
     /srv/rfo/
