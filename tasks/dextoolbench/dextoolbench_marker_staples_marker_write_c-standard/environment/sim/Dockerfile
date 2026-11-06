# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:mujoco-0.1.2
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.0@sha256:90253c4cb419668f84c6728dc6d6e23ea55ef8d7f7e7835a5eb65015729f91b0 /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:dextoolbench-files-0.4.1@sha256:06e51eb8f077ecedede92af0295f59d0709cab113d13145dc802e3a66724711e \
     /privileged/environment/rcb_dtb.py \
     /sim/server_mj.py \
     /srv/
