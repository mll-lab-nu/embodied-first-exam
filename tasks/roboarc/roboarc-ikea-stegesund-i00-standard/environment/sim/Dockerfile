# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:ikea-mujoco-sim-0.4.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:ikea-mujoco-files-0.5.0@sha256:31fc6ecc0ad00dd6554027c12adbe2af1ea124af085420284708ae9778c453d1 \
     /sim/finalize.sh \
     /sim/ikea_nyx.py \
     /sim/ikea_rig.py \
     /privileged/environment/rcb_ikea.py \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:roboarc-files-0.5.0@sha256:998a252f3ccef8fa99aebbfae8caebd5177f0c060d17aa0e6e57970c6e95f50d /nyx_direct.py /srv/nyx_direct.py
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.5.0@sha256:a6c2ac2ede9fe2c1744f9c6e67c6a49de9c5a8b8c2c9ae4f0d774b7dd72662ff \
     /rcb1.py \
     /v2_4/rcb_limited.py \
     /run.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:agent-end-files-0.1.1@sha256:af4fa3c2f87c31e67f03232d39ef54d82a0e06d57c23da1c56cd69936779b6d9 /rcb_agent_end.py /srv/rcb_agent_end.py
