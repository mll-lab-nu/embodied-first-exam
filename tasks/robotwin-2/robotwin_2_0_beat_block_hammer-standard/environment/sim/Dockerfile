# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:robotwin-0.1.2
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:6bf677373ff69d440d4640253caed50067929b8bf4a5d3a9c5f7315cd2752470 /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:robotwin-2-files-0.7.0@sha256:aac627addf7f53e2c775a26b232b13094c16d6353bc35fa71fdb094e79597042 \
     /sim/rcb_live.py \
     /sim/server.py \
     /srv/
