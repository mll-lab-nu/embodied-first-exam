# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.0-resetpose@sha256:90a9bd8fd47f66371cba9378ccc5954544457eab8dc60efe8d25dfb58ac329aa /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:pandadyn-files-0.4.0-resetpose@sha256:7f67caa107cabbfc9839b06cc8d5671de08d1d7d40dc2b1c8740dda01f9c63bb \
     /privileged/environment/rcb_pandadyn.py \
     /sim/rcb_service.py \
     /sim/server.py \
     /srv/
