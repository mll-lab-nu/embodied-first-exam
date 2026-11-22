# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:myosuite-0.1.1
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:myosuite-files-0.4.0-stateq@sha256:d17e72a5798e3f8da7966baaf83ee7cf424b24d4cfebbe2320d22bd68555d302 \
     /sim/finalize.sh \
     /privileged/environment/rcb_myosuite.py \
     /sim/video.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:myosuite-leakfix-files-0.1.0@sha256:76af1459494b565eb4ee2f99146f1fcbeed52d7a44e2639fae2262bb46c7bae5 \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.0-stateq@sha256:07fbf9e22ea11efd3398ef74d888ee7544410c1e07ff49e3fc5b8606b9acfe38 \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
