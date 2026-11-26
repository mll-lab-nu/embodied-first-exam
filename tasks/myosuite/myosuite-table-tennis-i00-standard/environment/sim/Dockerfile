# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:myosuite-0.1.1
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:myosuite-files-0.6.0@sha256:e4652741eed8cd129f4b9d71dbb3e8df9213d6818cef66aa88f6dcdbe393a738 \
     /sim/finalize.sh \
     /privileged/environment/rcb_myosuite.py \
     /sim/server.py \
     /sim/task.json \
     /sim/video.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.5.0@sha256:a6c2ac2ede9fe2c1744f9c6e67c6a49de9c5a8b8c2c9ae4f0d774b7dd72662ff \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:agent-end-files-0.1.1@sha256:af4fa3c2f87c31e67f03232d39ef54d82a0e06d57c23da1c56cd69936779b6d9 /rcb_agent_end.py /srv/rcb_agent_end.py
