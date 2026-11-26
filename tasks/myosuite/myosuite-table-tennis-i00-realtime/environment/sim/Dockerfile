# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:myosuite-0.1.1
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.5.0@sha256:d0f4045938a9683719f71de2342464216b53c49a87711923fb4afd551c081d82 \
     /rcb1.py \
     /realtime/rcb_realtime.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:myosuite-files-0.6.0@sha256:8130d2e62a65ff7e8b092823e84a64bb2b36ef6c7f04aa4b91e4242a9d3da33f \
     /privileged/environment/rcb_myosuite.py \
     /sim/rcb_service.py \
     /sim/task.json \
     /srv/
