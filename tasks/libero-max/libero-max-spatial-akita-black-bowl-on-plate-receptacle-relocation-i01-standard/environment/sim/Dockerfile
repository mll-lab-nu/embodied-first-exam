# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:libero-max-0.1.1
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:libero-max-files-0.7.0@sha256:8be6b43200f64f5451ab89c7fd21f6864466c1d287bc3ed3630e3d10e6260172 \
     /sim/finalize.sh \
     /privileged/environment/lmx_tool.py \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:6bf677373ff69d440d4640253caed50067929b8bf4a5d3a9c5f7315cd2752470 /sidecar/rcb_service.py /srv/rcb_service.py
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:6bf677373ff69d440d4640253caed50067929b8bf4a5d3a9c5f7315cd2752470 /rcb1.py /srv/rcb1.py
