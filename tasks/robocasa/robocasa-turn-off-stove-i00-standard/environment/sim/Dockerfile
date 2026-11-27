# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:robocasa-0.1.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:robocasa-files-0.6.0@sha256:6ad3a8a118370eb25a04dfabe42f1aa285d6c75afa7d9b29a8a1bd1eeb4a5088 \
     /privileged/environment/casa_tool.py \
     /sim/finalize.sh \
     /sim/server_casa.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.6.0@sha256:5e5e605d9f3cc2a4a0efc4ffb1f277278f8f77f225cc6ff60d00d15b4cb3b515 /rcb1.py /srv/rcb1.py
