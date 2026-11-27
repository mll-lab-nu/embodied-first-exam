# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:bigym2-0.1.1
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:497a2b864b3a1aaf1f60206dc14f08a0f99960037f0e54be3d4bc2e39f5adba4 /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:bigym2-files-0.8.0@sha256:dc58e642868b987ec37f4cb96ea91447c28e210f2c2954cde133afe6ca89977f \
     /privileged/environment/rcb_bigym2.py \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:497a2b864b3a1aaf1f60206dc14f08a0f99960037f0e54be3d4bc2e39f5adba4 /sidecar/rcb_service.py /srv/rcb_service.py
