# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:robocasa-gr1-0.1.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:robocasa-files-0.4.0-nosignal@sha256:987e6e75dc041d34168fa82a497bcb8c59405de60cc99af5eb600d88c0e7da00 /privileged/environment/casa_tool.py /srv/casa_tool.py
COPY --from=ghcr.io/mll-lab-nu/efe:robocasa-files-0.4.0-nosignal@sha256:987e6e75dc041d34168fa82a497bcb8c59405de60cc99af5eb600d88c0e7da00 \
     /sim/finalize.sh \
     /sim/server_casa.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.0-nosignal@sha256:9d9eb71b2baafac8d8a7975a78cca8e0e4f4ffd0aab700ed137653aa5f4e59d5 /rcb1.py /srv/rcb1.py
