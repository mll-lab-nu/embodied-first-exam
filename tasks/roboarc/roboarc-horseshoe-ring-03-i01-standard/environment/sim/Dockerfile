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
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:497a2b864b3a1aaf1f60206dc14f08a0f99960037f0e54be3d4bc2e39f5adba4 \
     /rcb1.py \
     /operations/rcb_limited.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:agent-end-files-0.5.0@sha256:3e1cda4a561e626b804231bf86efac77649926eabdfe8c930b8e2a01f35b74c3 /rcb_agent_end.py /srv/rcb_agent_end.py
