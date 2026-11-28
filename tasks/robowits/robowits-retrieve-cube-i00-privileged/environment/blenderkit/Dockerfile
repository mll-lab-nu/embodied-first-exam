# The `blenderkit` service's image (environment/docker-compose.yaml builds it): the base image and the task tooling
# (rcb_robowits.py blenderkit-serve) from the pinned files-only image, at the path the service runs it from.
FROM ghcr.io/mll-lab-nu/efe:robowits-0.1.1
COPY --from=ghcr.io/mll-lab-nu/efe:robowits-files-0.7.0@sha256:176315afdf4be26933b49bc175d51c9b46f348c7186ac3cd434878fbfc111b7d /privileged/tests/rcb_robowits.py /srv/rcb_robowits.py
