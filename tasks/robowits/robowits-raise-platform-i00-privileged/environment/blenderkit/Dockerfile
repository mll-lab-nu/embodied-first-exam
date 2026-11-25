# The `blenderkit` service's image (environment/docker-compose.yaml builds it): the base image and the task tooling
# (rcb_robowits.py blenderkit-serve) from the pinned files-only image, at the path the service runs it from.
FROM ghcr.io/mll-lab-nu/efe:robowits-0.1.1
COPY --from=ghcr.io/mll-lab-nu/efe:robowits-files-0.4.3@sha256:699e0a5451a3afa826672715382f1a9b4efef90dba8a65f50d2308a88b0eecc7 /privileged/tests/rcb_robowits.py /srv/rcb_robowits.py
