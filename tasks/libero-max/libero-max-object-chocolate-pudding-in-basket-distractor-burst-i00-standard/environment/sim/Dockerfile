# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:libero-max-0.1.1
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:libero-max-files-0.6.0@sha256:2cfd77f46ce13cd6ce02d17e7ee38f9fb062c0fbd54eb53b2938ab9e3264c479 \
     /sim/finalize.sh \
     /privileged/environment/lmx_tool.py \
     /sim/rcb_service.py \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.7.0@sha256:1ab8c16d4372a0b44f5c0ea7f819f6febafcfdc132013b1736a04f360375b28f /rcb1.py /srv/rcb1.py
