# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe-private:control-transfer-0.2.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.1@sha256:ec2520f7855f520bc032f24960306f290263adcf5c7d24e9083526d6584d2e7a \
     /sim/scripts/__init__.py \
     /standard/environment/public/control_public/client.py \
     /standard/environment/public/control_public/fly.py \
     /standard/environment/public/control_public/weights.py \
     /srv/control_public/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.1@sha256:ec2520f7855f520bc032f24960306f290263adcf5c7d24e9083526d6584d2e7a \
     /sim/neuralfly_constants.py \
     /standard/environment/public/neuralfly_nominal.py \
     /standard/environment/public/neuralfly_video.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.1@sha256:ec2520f7855f520bc032f24960306f290263adcf5c7d24e9083526d6584d2e7a /sim/scripts/__init__.py /srv/scripts/__init__.py
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.1@sha256:ec2520f7855f520bc032f24960306f290263adcf5c7d24e9083526d6584d2e7a \
     /sim/scripts/__init__.py \
     /sim/neuralfly_constants.py \
     /standard/environment/public/neuralfly_nominal.py \
     /standard/environment/public/neuralfly_video.py \
     /srv/scripts/control_transfer/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.1@sha256:ec2520f7855f520bc032f24960306f290263adcf5c7d24e9083526d6584d2e7a /sim/scripts/__init__.py /srv/scripts/control_transfer/components/__init__.py
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.1@sha256:ec2520f7855f520bc032f24960306f290263adcf5c7d24e9083526d6584d2e7a \
     /sim/scripts/__init__.py \
     /standard/environment/public/control_public/client.py \
     /standard/environment/public/control_public/fly.py \
     /standard/environment/public/control_public/weights.py \
     /srv/scripts/control_transfer/control_public/
