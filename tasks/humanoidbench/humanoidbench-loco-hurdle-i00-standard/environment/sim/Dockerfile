# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:humanoidbench-0.2.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.5.0@sha256:ff602baf1ef852d21ecf0152d94cf210c8b691a5bdaa88d00dc381f6150b98cb /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:humanoidbench-files-0.5.0@sha256:7d52321afdfbe0ecf4eb0817575794ec926bfacd7fa6c30be41f8de9b347d23f \
     /privileged/environment/rcb_hb.py \
     /privileged/tests/rcb_rewards.py \
     /sim/rcb_service.py \
     /sim/server.py \
     /srv/
