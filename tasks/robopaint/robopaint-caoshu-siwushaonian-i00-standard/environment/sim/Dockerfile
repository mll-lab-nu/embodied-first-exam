# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:robopaint-0.2.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:robopaint-files-0.9.0@sha256:be5b031c703c45784cbf30375c41e3f52737a2cb175d221f567d267972a6e970 \
     /sim/variants/d6118d094a/NOTICE-exemplar.md \
     /sim/finalize.sh \
     /rcb_brush.py \
     /rcb_brush_score.py \
     /rcb_brush_strict.py \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:497a2b864b3a1aaf1f60206dc14f08a0f99960037f0e54be3d4bc2e39f5adba4 \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:robopaint-pictures-files-0.1.0@sha256:3ce92526aa79918994ccb934390221e1dd6c3f4364109a40e5746140def6062e /caoshu-siwushaonian-i00/target.png /srv/target.png
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:497a2b864b3a1aaf1f60206dc14f08a0f99960037f0e54be3d4bc2e39f5adba4 /agent_end/rcb_agent_end.py /srv/rcb_agent_end.py
