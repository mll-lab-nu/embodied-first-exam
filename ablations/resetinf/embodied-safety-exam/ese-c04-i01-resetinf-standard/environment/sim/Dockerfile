# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:ese-0.5.6
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:ese-files-0.7.0-resetese@sha256:f170671a7ba06047ef542590d426566fd61a185750bac02b68368487baa119de \
     /standard/candidate_identity.py \
     /standard/picture_delivery.py \
     /standard/rcb_ese.py \
     /standard/rcb_service.py \
     /standard/replay.py \
     /standard/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.0-resetpose@sha256:90a9bd8fd47f66371cba9378ccc5954544457eab8dc60efe8d25dfb58ac329aa /rcb1.py /srv/rcb1.py
