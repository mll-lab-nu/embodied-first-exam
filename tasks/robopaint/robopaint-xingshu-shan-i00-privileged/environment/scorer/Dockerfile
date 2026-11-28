# The `scorer` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:robopaint-0.2.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:robopaint-files-0.9.0@sha256:0784a1af64aa0694b739edc8620d4f3e5becb57a2c73bef075fb80ee89e98a91 \
     /sim/variants/f948360d71/NOTICE-exemplar.md \
     /rcb_brush.py \
     /rcb_brush_score.py \
     /rcb_brush_strict.py \
     /sim/rcb_scorer.py \
     /sim/run.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:robopaint-pictures-files-0.1.0@sha256:3ce92526aa79918994ccb934390221e1dd6c3f4364109a40e5746140def6062e /xingshu-shan-i00/target.png /srv/target.png
