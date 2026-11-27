# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:mujoco-0.1.3
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:mujoco-playground-files-0.10.0@sha256:450a6892bef87b047a06f190b4c61d71ac0a01818ddc40fa49ed706ab78e055f \
     /sim/finalize.sh \
     /privileged/environment/rcb_quadruped.py \
     /sim/server.py \
     /sim/video.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:6bf677373ff69d440d4640253caed50067929b8bf4a5d3a9c5f7315cd2752470 \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:6bf677373ff69d440d4640253caed50067929b8bf4a5d3a9c5f7315cd2752470 /agent_end/rcb_agent_end.py /srv/rcb_agent_end.py
