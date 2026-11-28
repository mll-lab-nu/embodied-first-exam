# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:mujoco-0.1.2
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:a99b04e29e96564b62a2c335b191405d8a94785d6efea2bb5765acbefde92383 /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:dextoolbench-files-0.9.0@sha256:29efa37afe2d55d9c35b6791d4e73fcb79eb35ca88bfc7f0756ee4c9ffd90a57 \
     /privileged/environment/rcb_dtb.py \
     /sim/server_mj.py \
     /srv/
