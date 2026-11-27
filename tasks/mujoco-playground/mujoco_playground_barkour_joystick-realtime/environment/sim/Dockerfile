# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:mujoco-0.1.3
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.6.0@sha256:a5fa8a9d299f6027a84f45af38a297139ad8cf68231a911272064ee9c1edbb13 \
     /rcb1.py \
     /realtime/rcb_realtime.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:mujoco-playground-files-0.8.0@sha256:ad457cc15a9f4bf9a29b36856825f8834a5baf907b2c6b0c6de22b67470c1ce5 \
     /privileged/environment/rcb_quadruped.py \
     /sim/rcb_service.py \
     /srv/
