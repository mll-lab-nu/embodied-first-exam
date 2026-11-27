# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:metaworld-0.1.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:metaworldplus-files-0.8.0@sha256:7548af1c69100c873291a277e9c0963c1e4a44f41b41f75c8d530dbba11f4f9f \
     /privileged/environment/mw_tool.py \
     /sim/server_mw.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:6bf677373ff69d440d4640253caed50067929b8bf4a5d3a9c5f7315cd2752470 /rcb1.py /srv/rcb1.py
