# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:robowits-0.1.1
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.7.0@sha256:1ab8c16d4372a0b44f5c0ea7f819f6febafcfdc132013b1736a04f360375b28f \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:robowits-files-0.6.0@sha256:b6288da83664c4337ff6496a7656119fa8565bfc831c18bc03a3791c68fd9546 \
     /privileged/tests/rcb_robowits.py \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:agent-end-files-0.4.0@sha256:96a5c925a9128ed91e1654e2b9aac99373517c80c3aa5e47b8f74880a0c413d0 /rcb_agent_end.py /srv/rcb_agent_end.py
