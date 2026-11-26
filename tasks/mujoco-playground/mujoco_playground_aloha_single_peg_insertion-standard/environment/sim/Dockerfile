# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:mujoco-0.1.2
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.5.0@sha256:a6c2ac2ede9fe2c1744f9c6e67c6a49de9c5a8b8c2c9ae4f0d774b7dd72662ff /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:mujoco-playground-files-0.7.0@sha256:347e83daa4047f377fc94b83537d406fa4c5c6c79b6b18367aba47ccd652659b \
     /privileged/environment/rcb_aloha.py \
     /sim/server_mj.py \
     /srv/
