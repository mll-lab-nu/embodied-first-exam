# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:dexjoco-0.1.2
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:dexjoco-files-0.4.0@sha256:1faaee52683a3bf0f8f3719f2e022e9714d2be4bb56675e51b8b3a157316651d \
     /sim/finalize.sh \
     /privileged/environment/rcb_dexjoco.py \
     /sim/server.py \
     /sim/video.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.6.0@sha256:5e5e605d9f3cc2a4a0efc4ffb1f277278f8f77f225cc6ff60d00d15b4cb3b515 \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:agent-end-files-0.3.0@sha256:06f4caf4617d33158edc8ccb7b4ac5dfc607da5e1d51776ec16d0bd2d72b00ff /rcb_agent_end.py /srv/rcb_agent_end.py
