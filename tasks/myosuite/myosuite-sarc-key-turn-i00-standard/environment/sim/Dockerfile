# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:myosuite-0.1.1
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:myosuite-files-0.9.0@sha256:1a0d096942399d847e09df0d3b2e6b312542b2a5481a374061a87df9f6fffefa \
     /sim/finalize.sh \
     /privileged/environment/rcb_myosuite.py \
     /sim/server.py \
     /sim/video.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.9.0@sha256:2cf5b6f826d698eaa0dcddf1561e6c673ca0ddabac2c3868d823598eb3cb75b6 \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.9.0@sha256:2cf5b6f826d698eaa0dcddf1561e6c673ca0ddabac2c3868d823598eb3cb75b6 /agent_end/rcb_agent_end.py /srv/rcb_agent_end.py
