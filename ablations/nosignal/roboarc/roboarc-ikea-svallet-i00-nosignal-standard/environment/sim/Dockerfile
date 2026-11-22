# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:ikea-mujoco-sim-0.4.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:ikea-mujoco-files-0.4.0-nosignal@sha256:9c8e34a66e78ca372fa4687a61536e8bb2ce8a204036ca6e19b8310f85ec4d67 \
     /sim/finalize.sh \
     /sim/ikea_nyx.py \
     /sim/ikea_rig.py \
     /privileged/environment/rcb_ikea.py \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:roboarc-files-0.4.0-nosignal2@sha256:afef6dc0e2fe4a8025139c1efcff649baa7fd3c38b46eedff1b40e663855ebbe /nyx_direct.py /srv/nyx_direct.py
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.0-nosignal@sha256:9d9eb71b2baafac8d8a7975a78cca8e0e4f4ffd0aab700ed137653aa5f4e59d5 \
     /rcb1.py \
     /v2_4/rcb_limited.py \
     /run.sh \
     /srv/
