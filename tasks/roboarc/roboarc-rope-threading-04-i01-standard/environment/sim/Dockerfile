# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:roboarc-0.2.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:roboarc-files-0.7.0@sha256:ac0a5ee307d990c3f76c979f838799f25450a3c006e7d18de42992ddaa7d21a5 \
     /standard/sim/finalize.sh \
     /nyx_direct.py \
     /rcb_topogym.py \
     /render_bridge.py \
     /standard/sim/replay.py \
     /sim/run.sh \
     /standard/sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.7.0@sha256:1ab8c16d4372a0b44f5c0ea7f819f6febafcfdc132013b1736a04f360375b28f \
     /rcb1.py \
     /v2_4/rcb_limited.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:agent-end-files-0.4.0@sha256:96a5c925a9128ed91e1654e2b9aac99373517c80c3aa5e47b8f74880a0c413d0 /rcb_agent_end.py /srv/rcb_agent_end.py
