# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:bigym2-0.1.1
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.0-nosignal@sha256:9d9eb71b2baafac8d8a7975a78cca8e0e4f4ffd0aab700ed137653aa5f4e59d5 /rcb1.py /srv/rcb1.py
COPY --from=ghcr.io/mll-lab-nu/efe:bigym2-files-0.4.0-nosignal@sha256:97cb9332f053652aaa3125e7b27eebc937d48e5990f58e2531a544668ff1cadf \
     /privileged/environment/rcb_bigym2.py \
     /sim/rcb_service.py \
     /sim/server.py \
     /srv/
