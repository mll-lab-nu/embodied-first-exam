# The `blenderkit` service's image (environment/docker-compose.yaml builds it): the base image and the task tooling
# (rcb_robowits.py blenderkit-serve) from the pinned files-only image, at the path the service runs it from.
FROM ghcr.io/mll-lab-nu/efe:robowits-0.1.1
COPY --from=ghcr.io/mll-lab-nu/efe:robowits-files-0.4.3@sha256:6dff7e7072f6ab4b71f991b93a54c1152fb47270241826d0802213a39c79e896 /privileged/tests/rcb_robowits.py /srv/rcb_robowits.py
