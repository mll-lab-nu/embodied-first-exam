# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:dexjoco-0.1.2
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:dexjoco-files-0.2.0-stateq@sha256:2fb7a19a80453ccfffdc2aeffa2a4d0e47e8dce83e335266c6095d3fb390dbbc \
     /sim/finalize.sh \
     /privileged/environment/rcb_dexjoco.py \
     /sim/video.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:dexjoco-leakfix-files-0.1.0@sha256:4d7987e11e76ff869b4478a6aef59229212906f5fbe3c2d9acd54900b2420716 \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.0-stateq@sha256:07fbf9e22ea11efd3398ef74d888ee7544410c1e07ff49e3fc5b8606b9acfe38 \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
