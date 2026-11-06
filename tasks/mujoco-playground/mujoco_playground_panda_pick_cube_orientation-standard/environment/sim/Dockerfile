# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:mujoco-0.1.2
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.0@sha256:90253c4cb419668f84c6728dc6d6e23ea55ef8d7f7e7835a5eb65015729f91b0 /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:mujoco-playground-files-0.5.1@sha256:9990d2f1e2f7771f2da16ad8f69e07b06a2e8a989ff51f02489178ed0b87fbae \
     /privileged/environment/rcb_panda.py \
     /sim/server_mj.py \
     /srv/
