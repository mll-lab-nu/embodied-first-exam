# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:mujoco-0.1.2
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.0-stateq@sha256:07fbf9e22ea11efd3398ef74d888ee7544410c1e07ff49e3fc5b8606b9acfe38 /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:mujoco-playground-files-0.5.0-stateq@sha256:757618ac9f11c2c39f4bd879eabc484a96f7be83b22e629665f21c696e60ebb5 \
     /privileged/environment/rcb_aloha.py \
     /sim/server_mj.py \
     /srv/
