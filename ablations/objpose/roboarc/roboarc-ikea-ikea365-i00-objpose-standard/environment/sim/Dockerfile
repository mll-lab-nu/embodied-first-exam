# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:ikea-mujoco-sim-0.4.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:ikea-mujoco-files-0.4.0-stateq@sha256:7d11b140b06146b3db96743726c9ce7196e04cc9ed41cf75fe99e209679bdcbc \
     /sim/finalize.sh \
     /sim/ikea_nyx.py \
     /sim/ikea_rig.py \
     /privileged/environment/rcb_ikea.py \
     /sim/rig.json \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:roboarc-files-0.4.0-stateq@sha256:20b83eb467f5b4f58504c96abeff4fa7c12dd9c5b0ca0c5d80a32d2c87480f5e /nyx_direct.py /srv/nyx_direct.py
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.0-stateq@sha256:07fbf9e22ea11efd3398ef74d888ee7544410c1e07ff49e3fc5b8606b9acfe38 \
     /rcb1.py \
     /v2_4/rcb_limited.py \
     /run.sh \
     /srv/
