# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:robowits-0.1.1
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.0-stateq@sha256:07fbf9e22ea11efd3398ef74d888ee7544410c1e07ff49e3fc5b8606b9acfe38 \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:robowits-files-0.4.0-stateq@sha256:c97b8eae087ca3a5fdebeb8d9f1f24ba7861b9d4f1db7a682e008852c15e2671 \
     /privileged/tests/rcb_robowits.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:robowits-leakfix-files-0.1.0@sha256:e2769a6547754d78956e609cc7aa31445401b86157bf44ce996d1ede1369fc1f \
     /sim/server.py \
     /srv/
