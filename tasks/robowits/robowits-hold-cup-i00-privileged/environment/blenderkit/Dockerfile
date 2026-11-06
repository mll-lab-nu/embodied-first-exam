# The `blenderkit` service's image (environment/docker-compose.yaml builds it): the base image and the task tooling
# (rcb_robowits.py blenderkit-serve) from the pinned files-only image, at the path the service runs it from.
FROM ghcr.io/mll-lab-nu/efe:robowits-0.1.1
COPY --from=ghcr.io/mll-lab-nu/efe:robowits-files-0.4.1@sha256:b19fe9b88e76bedcda3de829235a451bb3e44c6bc7b214b49e251dbea23c09f0 /privileged/tests/rcb_robowits.py /srv/rcb_robowits.py
