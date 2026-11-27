# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:mujoco-0.1.2
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.6.0@sha256:5e5e605d9f3cc2a4a0efc4ffb1f277278f8f77f225cc6ff60d00d15b4cb3b515 /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:dextoolbench-files-0.7.0@sha256:7ef13efc48a04106d32e2dbd6127cd2d731cab1e4d439c88b90d34826256b191 \
     /privileged/environment/rcb_dtb.py \
     /sim/server_mj.py \
     /srv/
