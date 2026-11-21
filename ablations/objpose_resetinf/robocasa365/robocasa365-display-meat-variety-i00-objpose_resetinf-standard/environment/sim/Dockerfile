# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:robocasa365-0.1.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:robocasa365-files-0.5.0-stateq@sha256:5cdf2430aff4f1254bbe9d332c555823e3ceaa972469cbb43f793914d79ff3e9 \
     /privileged/environment/casa_tool.py \
     /sim/finalize.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:robocasa365-leakfix-files-0.1.0@sha256:3b767e38180d1406673de3442bf8fa1e2751c5e79e4ff2f9ab6fff50dce500c7 \
     /sim/server_casa.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.0-stateq@sha256:07fbf9e22ea11efd3398ef74d888ee7544410c1e07ff49e3fc5b8606b9acfe38 /rcb1.py /srv/rcb1.py
