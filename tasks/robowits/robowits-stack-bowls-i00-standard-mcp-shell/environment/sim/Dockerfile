# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:robowits-0.1.1
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.1@sha256:7f1a830075fd6dd25e7a20a340316c041df583a29062796f59a4fa63b6f76946 \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:robowits-files-0.4.2@sha256:0c7ba52e4ba979a623776833ccd95c33802c72902acfa9efc0ce68dc7c31898a \
     /privileged/tests/rcb_robowits.py \
     /sim/server.py \
     /srv/
