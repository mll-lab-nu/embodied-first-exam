# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:ikea-mujoco-sim-0.4.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:ikea-mujoco-files-0.5.0@sha256:e0fb14a1db1ae5ddcf4096e0fac23ea76772056ac218c841e6c253dfb8c92e9e \
     /sim/finalize.sh \
     /sim/ikea_nyx.py \
     /sim/ikea_rig.py \
     /privileged/environment/rcb_ikea.py \
     /sim/rig.json \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:roboarc-files-0.6.0@sha256:016aa551e479510f34aa55686da7adc75c999fcc1b0d03e944056e1b30f46faf /nyx_direct.py /srv/nyx_direct.py
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.6.0@sha256:5e5e605d9f3cc2a4a0efc4ffb1f277278f8f77f225cc6ff60d00d15b4cb3b515 \
     /rcb1.py \
     /v2_4/rcb_limited.py \
     /run.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:agent-end-files-0.3.0@sha256:06f4caf4617d33158edc8ccb7b4ac5dfc607da5e1d51776ec16d0bd2d72b00ff /rcb_agent_end.py /srv/rcb_agent_end.py
