# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:robopaint-0.2.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:robopaint-files-0.9.0@sha256:6c558aeaeddd1936ba884ee43161c3c54b723670c26b88dfe45cdba041ec2db9 \
     /sim/NOTICE-exemplar.md \
     /sim/finalize.sh \
     /rcb_brush.py \
     /rcb_brush_score.py \
     /rcb_brush_strict.py \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:a99b04e29e96564b62a2c335b191405d8a94785d6efea2bb5765acbefde92383 \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:robopaint-pictures-files-0.1.0@sha256:3ce92526aa79918994ccb934390221e1dd6c3f4364109a40e5746140def6062e /acrylic-bluehorses-i00/target.png /srv/target.png
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:a99b04e29e96564b62a2c335b191405d8a94785d6efea2bb5765acbefde92383 /agent_end/rcb_agent_end.py /srv/rcb_agent_end.py
