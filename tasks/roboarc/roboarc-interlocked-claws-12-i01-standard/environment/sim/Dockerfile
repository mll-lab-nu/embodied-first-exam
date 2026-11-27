# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:roboarc-0.2.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:roboarc-files-0.8.0@sha256:906e6db4747259bf83aa9454b720765d155ff2c6b578ed06b815c8ef3146896e \
     /standard/sim/finalize.sh \
     /nyx_direct.py \
     /rcb_topogym.py \
     /render_bridge.py \
     /standard/sim/replay.py \
     /sim/run.sh \
     /standard/sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:6bf677373ff69d440d4640253caed50067929b8bf4a5d3a9c5f7315cd2752470 \
     /rcb1.py \
     /operations/rcb_limited.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:6bf677373ff69d440d4640253caed50067929b8bf4a5d3a9c5f7315cd2752470 /agent_end/rcb_agent_end.py /srv/rcb_agent_end.py
