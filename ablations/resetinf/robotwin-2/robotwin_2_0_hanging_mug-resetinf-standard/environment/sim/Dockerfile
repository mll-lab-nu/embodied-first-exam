# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:robotwin-0.1.2
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.0-resetpose@sha256:90a9bd8fd47f66371cba9378ccc5954544457eab8dc60efe8d25dfb58ac329aa /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:robotwin-2-files-0.3.0-resetpose@sha256:05bcac93abacc52a8a201420896a0aa93cc2588612391061aa5f7199b45a39be \
     /sim/rcb_live.py \
     /sim/server.py \
     /srv/
