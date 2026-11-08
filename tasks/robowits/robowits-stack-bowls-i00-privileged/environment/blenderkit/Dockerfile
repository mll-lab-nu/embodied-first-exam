# The `blenderkit` service's image (environment/docker-compose.yaml builds it): the base image and the task tooling
# (rcb_robowits.py blenderkit-serve) from the pinned files-only image, at the path the service runs it from.
FROM ghcr.io/mll-lab-nu/efe:robowits-0.1.1
COPY --from=ghcr.io/mll-lab-nu/efe:robowits-files-0.4.2@sha256:0c7ba52e4ba979a623776833ccd95c33802c72902acfa9efc0ce68dc7c31898a /privileged/tests/rcb_robowits.py /srv/rcb_robowits.py
