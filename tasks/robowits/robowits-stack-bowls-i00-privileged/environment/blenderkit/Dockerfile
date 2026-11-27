# The `blenderkit` service's image (environment/docker-compose.yaml builds it): the base image and the task tooling
# (rcb_robowits.py blenderkit-serve) from the pinned files-only image, at the path the service runs it from.
FROM ghcr.io/mll-lab-nu/efe:robowits-0.1.1
COPY --from=ghcr.io/mll-lab-nu/efe:robowits-files-0.7.0@sha256:ce770ea26b8713a44994c36801d208d99ae44b558b5d2c5b8f40f7d8825cfdb2 /privileged/tests/rcb_robowits.py /srv/rcb_robowits.py
