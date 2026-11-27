# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:metaworld-0.1.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:metaworldplus-files-0.7.0@sha256:dd67693dfec528031322e6a918bce758484462030e80a940d1fe08acbafbdc13 \
     /privileged/environment/mw_tool.py \
     /sim/server_mw.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:8a712f54d69d3fb089573d962c0756ef1026119a4337be28785e4a14410d20b3 /rcb1.py /srv/rcb1.py
