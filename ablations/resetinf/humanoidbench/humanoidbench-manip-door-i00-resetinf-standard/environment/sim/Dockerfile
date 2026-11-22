# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:humanoidbench-0.2.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.0-resetpose@sha256:90a9bd8fd47f66371cba9378ccc5954544457eab8dc60efe8d25dfb58ac329aa /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:humanoidbench-files-0.4.0-resetpose@sha256:9c587f783c089245b441d40ce6f5a4587cfa5fcb6ee05f2fdf2cbafa6b963a33 \
     /privileged/environment/rcb_hb.py \
     /privileged/tests/rcb_rewards.py \
     /sim/rcb_service.py \
     /sim/server.py \
     /srv/
