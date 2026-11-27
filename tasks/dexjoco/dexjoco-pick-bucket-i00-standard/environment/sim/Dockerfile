# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:dexjoco-0.1.2
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:dexjoco-files-0.7.0@sha256:cb5c3cb0c303d3a3545650a1ba1b0c6048c10e80d031cf038506f21f838219be \
     /sim/finalize.sh \
     /privileged/environment/rcb_dexjoco.py \
     /sim/server.py \
     /sim/video.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:8a712f54d69d3fb089573d962c0756ef1026119a4337be28785e4a14410d20b3 \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:agent-end-files-0.5.0@sha256:b6943584134a0cabb6d0a42a7a4e5e617be92c7299468e90a6021a023b6e557e /rcb_agent_end.py /srv/rcb_agent_end.py
