# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:robopaint-0.2.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:robopaint-files-0.6.0@sha256:6cb7d4829212ff3b2afb320d02f538d3f259da19ba11158c8978ab0ca46a28c9 \
     /sim/ARPHICPL.TXT \
     /sim/variants/16c0bbe684/NOTICE-exemplar.md \
     /sim/finalize.sh \
     /rcb_brush.py \
     /rcb_brush_score.py \
     /rcb_brush_strict.py \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.5.0@sha256:d0f4045938a9683719f71de2342464216b53c49a87711923fb4afd551c081d82 \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:robopaint-pictures-files-0.1.0@sha256:3ce92526aa79918994ccb934390221e1dd6c3f4364109a40e5746140def6062e /kaishu-yongzibafa-i00/target.png /srv/target.png
COPY --from=ghcr.io/mll-lab-nu/efe:agent-end-files-0.2.0@sha256:85bb0e3d2a49a8c94d1cefa47d8556d96b9d4afa528fd5ea9532cf53cb79a6e6 /rcb_agent_end.py /srv/rcb_agent_end.py
