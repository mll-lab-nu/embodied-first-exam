# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:roboarc-0.2.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:roboarc-files-0.5.0@sha256:bdb269686718ac525006bf9c8befd3a24cb027337416c3a1aaefbc44369f9318 \
     /standard/sim/finalize.sh \
     /nyx_direct.py \
     /rcb_topogym.py \
     /render_bridge.py \
     /standard/sim/replay.py \
     /sim/run.sh \
     /standard/sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.5.0@sha256:d0f4045938a9683719f71de2342464216b53c49a87711923fb4afd551c081d82 \
     /rcb1.py \
     /v2_4/rcb_limited.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:agent-end-files-0.2.0@sha256:85bb0e3d2a49a8c94d1cefa47d8556d96b9d4afa528fd5ea9532cf53cb79a6e6 /rcb_agent_end.py /srv/rcb_agent_end.py
