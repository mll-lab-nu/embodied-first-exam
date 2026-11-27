# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:myosuite-0.1.1
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:8a712f54d69d3fb089573d962c0756ef1026119a4337be28785e4a14410d20b3 \
     /rcb1.py \
     /realtime/rcb_realtime.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:myosuite-files-0.9.0@sha256:ac495582d703fef1a000932aa461f1bb2500a79c1ac503025a9683becde529d8 \
     /privileged/environment/rcb_myosuite.py \
     /sim/rcb_service.py \
     /sim/task.json \
     /srv/
