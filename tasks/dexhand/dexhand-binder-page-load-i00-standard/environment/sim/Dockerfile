# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-sim-files-0.1.1@sha256:676fccc44be31a72ac06e4b1f59f59d05671bc68e141cdfe80fa5aee25cb3df5 \
     /sim/finalize.py \
     /sim/finalize.sh \
     /privileged/environment/hands.py \
     /sim/rcb_dexhand.py \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-sim-files-0.1.1@sha256:d9a4e130a67056d0fb47594562ac303b2f000c5f48fbe5ec235593bef0f3543f \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
