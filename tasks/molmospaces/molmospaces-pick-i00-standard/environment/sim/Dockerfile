# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:molmospaces-0.2.5
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:molmospaces-files-0.8.0@sha256:df5e63c1f7f6c785e7072159ae05adb0a221d6ed1d26409afadf37eb78d485de \
     /sim/finalize.sh \
     /privileged/environment/rcb_molmospaces.py \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:8a712f54d69d3fb089573d962c0756ef1026119a4337be28785e4a14410d20b3 \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:agent-end-files-0.5.0@sha256:b6943584134a0cabb6d0a42a7a4e5e617be92c7299468e90a6021a023b6e557e /rcb_agent_end.py /srv/rcb_agent_end.py
