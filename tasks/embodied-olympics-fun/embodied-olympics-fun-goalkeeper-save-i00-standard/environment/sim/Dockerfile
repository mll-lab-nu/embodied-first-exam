# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.7.0@sha256:c874478c11ee71ad10506a63176949b65168c757a45a2af6ebdc93e43dd2fdf4 /rfo/tasks/goalkeeper_save.py /srv/rfo_task.py
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.6.0@sha256:5e5e605d9f3cc2a4a0efc4ffb1f277278f8f77f225cc6ff60d00d15b4cb3b515 /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.7.0@sha256:c874478c11ee71ad10506a63176949b65168c757a45a2af6ebdc93e43dd2fdf4 \
     /rcb_rfo.py \
     /standard/rcb_service.py \
     /standard/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-files-0.7.0@sha256:c874478c11ee71ad10506a63176949b65168c757a45a2af6ebdc93e43dd2fdf4 \
     /rfo/__init__.py \
     /rfo/looks.py \
     /rfo/realhand.py \
     /rfo/referee.py \
     /rfo/scene.py \
     /rfo/task.py \
     /rfo/world.py \
     /srv/rfo/
