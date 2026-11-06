# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:metaworld-0.1.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:metaworldplus-files-0.4.1@sha256:38f72c63924875c5cbd6f71253ddfe3123dcd0fbfede60b3b18d1e225b393bd6 \
     /privileged/environment/mw_tool.py \
     /sim/server_mw.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.1@sha256:7f1a830075fd6dd25e7a20a340316c041df583a29062796f59a4fa63b6f76946 /rcb1.py /srv/rcb1.py
