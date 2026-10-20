# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe-private:control-transfer-0.2.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-sim-files-0.1.1@sha256:ff5d835cd1c0872f583144aab4caa01a18256cb6d99224c25aea18d55b53b0ed \
     /sim/scripts/__init__.py \
     /standard/environment/public/control_public/client.py \
     /standard/environment/public/control_public/fly.py \
     /standard/environment/public/control_public/weights.py \
     /srv/control_public/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-sim-files-0.1.1@sha256:ff5d835cd1c0872f583144aab4caa01a18256cb6d99224c25aea18d55b53b0ed \
     /sim/neuralfly_constants.py \
     /standard/environment/public/neuralfly_nominal.py \
     /standard/environment/public/neuralfly_video.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-sim-files-0.1.1@sha256:ff5d835cd1c0872f583144aab4caa01a18256cb6d99224c25aea18d55b53b0ed /sim/scripts/__init__.py /srv/scripts/__init__.py
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-sim-files-0.1.1@sha256:ff5d835cd1c0872f583144aab4caa01a18256cb6d99224c25aea18d55b53b0ed \
     /sim/scripts/__init__.py \
     /sim/neuralfly_constants.py \
     /standard/environment/public/neuralfly_nominal.py \
     /standard/environment/public/neuralfly_video.py \
     /srv/scripts/control_transfer/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-sim-files-0.1.1@sha256:ff5d835cd1c0872f583144aab4caa01a18256cb6d99224c25aea18d55b53b0ed /sim/scripts/__init__.py /srv/scripts/control_transfer/components/__init__.py
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-sim-files-0.1.1@sha256:ff5d835cd1c0872f583144aab4caa01a18256cb6d99224c25aea18d55b53b0ed \
     /sim/scripts/__init__.py \
     /standard/environment/public/control_public/client.py \
     /standard/environment/public/control_public/fly.py \
     /standard/environment/public/control_public/weights.py \
     /srv/scripts/control_transfer/control_public/
