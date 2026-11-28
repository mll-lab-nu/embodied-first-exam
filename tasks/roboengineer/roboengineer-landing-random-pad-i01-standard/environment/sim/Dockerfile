# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe-private:quadrotor-landing-0.1.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.4.0@sha256:710f5232e0c81ad59397c1612cc015a471cb3f0fe12a1599ad11d888b80d3609 /sim/scripts/__init__.py /srv/scripts/__init__.py
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.4.0@sha256:710f5232e0c81ad59397c1612cc015a471cb3f0fe12a1599ad11d888b80d3609 /sim/scripts/__init__.py /srv/scripts/quadrotor_landing/__init__.py
COPY --from=ghcr.io/mll-lab-nu/efe:roboengineer-files-0.4.0@sha256:710f5232e0c81ad59397c1612cc015a471cb3f0fe12a1599ad11d888b80d3609 \
     /sim/scripts/__init__.py \
     /standard/environment/public/scripts/quadrotor_landing/public/client.py \
     /standard/environment/public/scripts/quadrotor_landing/public/model.py \
     /standard/environment/public/scripts/quadrotor_landing/public/nominal.py \
     /standard/environment/public/scripts/quadrotor_landing/public/policy.py \
     /srv/scripts/quadrotor_landing/public/
