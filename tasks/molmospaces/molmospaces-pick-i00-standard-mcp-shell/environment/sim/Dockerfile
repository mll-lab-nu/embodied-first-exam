# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:molmospaces-0.2.5
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:molmospaces-files-0.5.0@sha256:ea993336748fd6f3c8801d15d275ec90fd7a0e89ff0d1dadc07663f722b81800 \
     /sim/finalize.sh \
     /privileged/environment/rcb_molmospaces.py \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.1@sha256:7f1a830075fd6dd25e7a20a340316c041df583a29062796f59a4fa63b6f76946 \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
