# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:mujoco-0.1.2
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.5.0@sha256:d0f4045938a9683719f71de2342464216b53c49a87711923fb4afd551c081d82 /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:mujoco-playground-files-0.7.0@sha256:931d2b59ff197790ac2d917f047334a485f1ae272753ab4ba5de7612aa7edf6d \
     /privileged/environment/rcb_panda.py \
     /sim/server_mj.py \
     /srv/
