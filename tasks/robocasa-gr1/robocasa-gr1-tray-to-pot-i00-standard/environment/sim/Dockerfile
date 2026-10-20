# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:robocasa-gr1-0.1.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:robocasa-files-0.1.1@sha256:085a6fe1c9316f02288cd372128accb0b0e1cdade86e64e35884ab9bc583fc56 /privileged/environment/casa_tool.py /srv/casa_tool.py
COPY --from=ghcr.io/mll-lab-nu/efe:robocasa-gr1-sim-files-0.1.1@sha256:78683e4934958f003961a37d9f3da2d37b2f8fa0d091fc0aa90be496466768fb \
     /sim/finalize.sh \
     /sim/server_casa.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-sim-files-0.1.1@sha256:d9a4e130a67056d0fb47594562ac303b2f000c5f48fbe5ec235593bef0f3543f /rcb1.py /srv/rcb1.py
