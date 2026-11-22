# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe-private:control-transfer-0.2.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.0-abl-pose@sha256:29dcec8ca59eb0522c6676c6157ee67c34f7b839458b2adc4ebfd5cc0ca29d6e /anycarbench/ /srv/anycarbench/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.0-abl-pose@sha256:29dcec8ca59eb0522c6676c6157ee67c34f7b839458b2adc4ebfd5cc0ca29d6e /anycarbench/ /srv/scripts/control_transfer/components/anycarbench/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.0-abl-pose@sha256:29dcec8ca59eb0522c6676c6157ee67c34f7b839458b2adc4ebfd5cc0ca29d6e /sim/control_assets.py /srv/control_assets.py
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.0-abl-pose@sha256:29dcec8ca59eb0522c6676c6157ee67c34f7b839458b2adc4ebfd5cc0ca29d6e \
     /sim/scripts/__init__.py \
     /standard/environment/public/control_public/anycar.py \
     /standard/environment/public/control_public/anycar_drift.py \
     /standard/environment/public/control_public/anycar_drift_nominal.py \
     /standard/environment/public/control_public/client.py \
     /standard/environment/public/control_public/weights.py \
     /srv/control_public/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.0-abl-pose@sha256:29dcec8ca59eb0522c6676c6157ee67c34f7b839458b2adc4ebfd5cc0ca29d6e /sim/scripts/__init__.py /srv/scripts/__init__.py
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.0-abl-pose@sha256:29dcec8ca59eb0522c6676c6157ee67c34f7b839458b2adc4ebfd5cc0ca29d6e \
     /sim/scripts/__init__.py \
     /sim/scripts/control_transfer/anycar_drift_spec.py \
     /sim/scripts/control_transfer/anycar_spec.py \
     /srv/scripts/control_transfer/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.0-abl-pose@sha256:29dcec8ca59eb0522c6676c6157ee67c34f7b839458b2adc4ebfd5cc0ca29d6e /sim/scripts/__init__.py /srv/scripts/control_transfer/components/__init__.py
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.3.0-abl-pose@sha256:29dcec8ca59eb0522c6676c6157ee67c34f7b839458b2adc4ebfd5cc0ca29d6e \
     /sim/scripts/__init__.py \
     /standard/environment/public/control_public/anycar.py \
     /standard/environment/public/control_public/anycar_drift.py \
     /standard/environment/public/control_public/anycar_drift_nominal.py \
     /standard/environment/public/control_public/client.py \
     /standard/environment/public/control_public/weights.py \
     /srv/scripts/control_transfer/control_public/
