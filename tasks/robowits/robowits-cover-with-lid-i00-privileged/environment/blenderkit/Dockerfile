# The `blenderkit` service's image (environment/docker-compose.yaml builds it): the base image and the task tooling
# (rcb_robowits.py blenderkit-serve) from the pinned files-only image, at the path the service runs it from.
FROM ghcr.io/mll-lab-nu/efe:robowits-0.1.1
COPY --from=ghcr.io/mll-lab-nu/efe:robowits-files-0.4.0@sha256:efc96cd1f591e69d0005326dec61c3644065943a9b2a04905fc2a68a4c400dca /privileged/tests/rcb_robowits.py /srv/rcb_robowits.py
