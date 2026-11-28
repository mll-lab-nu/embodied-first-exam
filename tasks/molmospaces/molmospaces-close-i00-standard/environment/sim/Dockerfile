# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:molmospaces-0.2.5
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:molmospaces-files-0.8.0@sha256:585b6553aef9333a610c08b03e880c56c7e756820e9870c62fce3a46a7e8cad4 \
     /sim/finalize.sh \
     /privileged/environment/rcb_molmospaces.py \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:a99b04e29e96564b62a2c335b191405d8a94785d6efea2bb5765acbefde92383 \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:a99b04e29e96564b62a2c335b191405d8a94785d6efea2bb5765acbefde92383 /agent_end/rcb_agent_end.py /srv/rcb_agent_end.py
