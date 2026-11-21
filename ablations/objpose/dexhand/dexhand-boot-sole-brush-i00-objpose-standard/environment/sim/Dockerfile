# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.4.0-stateq@sha256:21852e2ab6751b6f200608173cc10f64296b1b49be905d3eb7158f26fa2a4149 \
     /privileged/environment/arm_rig.py \
     /sim/finalize.py \
     /sim/finalize.sh \
     /privileged/environment/hands.py \
     /sim/rcb_dexhand.py \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.0-stateq@sha256:07fbf9e22ea11efd3398ef74d888ee7544410c1e07ff49e3fc5b8606b9acfe38 \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
