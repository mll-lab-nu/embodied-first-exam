# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:myosuite-0.1.1
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:myosuite-files-0.9.0@sha256:0c117fc5b3cc181458f46f7b9981789e431a21d34ba608cd5726c931e3ced173 \
     /sim/finalize.sh \
     /privileged/environment/rcb_myosuite.py \
     /sim/server.py \
     /sim/video.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:a99b04e29e96564b62a2c335b191405d8a94785d6efea2bb5765acbefde92383 \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:a99b04e29e96564b62a2c335b191405d8a94785d6efea2bb5765acbefde92383 /agent_end/rcb_agent_end.py /srv/rcb_agent_end.py
