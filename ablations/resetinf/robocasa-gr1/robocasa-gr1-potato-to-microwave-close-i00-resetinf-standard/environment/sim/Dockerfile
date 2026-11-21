# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:robocasa-gr1-0.1.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:robocasa-files-0.4.0-resetpose@sha256:f8b81b951fb0fc0aa40f270670473d448d4be89c9959c400f06e6271b7df13d4 /privileged/environment/casa_tool.py /srv/casa_tool.py
COPY --from=ghcr.io/mll-lab-nu/efe:robocasa-files-0.4.0-resetpose@sha256:f8b81b951fb0fc0aa40f270670473d448d4be89c9959c400f06e6271b7df13d4 \
     /sim/finalize.sh \
     /sim/server_casa.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.0-resetpose@sha256:90a9bd8fd47f66371cba9378ccc5954544457eab8dc60efe8d25dfb58ac329aa /rcb1.py /srv/rcb1.py
