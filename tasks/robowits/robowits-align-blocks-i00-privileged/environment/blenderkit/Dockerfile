# The `blenderkit` service's image (environment/docker-compose.yaml builds it): the base image and the task tooling
# (rcb_robowits.py blenderkit-serve) from the pinned files-only image, at the path the service runs it from.
FROM ghcr.io/mll-lab-nu/efe:robowits-0.1.1
COPY --from=ghcr.io/mll-lab-nu/efe:robowits-files-0.5.0@sha256:8aa1b1ffe3a16aeabdd390a99dfcbddc912c9e19417000a75392b7d0792eb8cb /privileged/tests/rcb_robowits.py /srv/rcb_robowits.py
