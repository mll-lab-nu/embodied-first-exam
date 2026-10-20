# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:ese-0.5.6
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-safety-exam-sim-files-0.1.1@sha256:61c160e5550140242fd4660bafd2b42852590ede2859ee390aa8fd6ac7615a41 \
     /standard/candidate_identity.py \
     /standard/picture_delivery.py \
     /standard/rcb_ese.py \
     /standard/rcb_service.py \
     /standard/replay.py \
     /standard/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-sim-files-0.1.1@sha256:d9a4e130a67056d0fb47594562ac303b2f000c5f48fbe5ec235593bef0f3543f /rcb1.py /srv/rcb1.py
