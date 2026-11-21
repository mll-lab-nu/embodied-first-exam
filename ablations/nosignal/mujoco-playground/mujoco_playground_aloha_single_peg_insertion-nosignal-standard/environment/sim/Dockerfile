# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:mujoco-0.1.2
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.0-nosignal@sha256:9d9eb71b2baafac8d8a7975a78cca8e0e4f4ffd0aab700ed137653aa5f4e59d5 /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:mujoco-playground-files-0.5.0-nosignal@sha256:e3204d4459cf63862f3f1a339f4ac6f6f0b197bc74acbce78e944f24e4e66110 \
     /privileged/environment/rcb_aloha.py \
     /sim/server_mj.py \
     /srv/
