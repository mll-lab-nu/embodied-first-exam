# The `blenderkit` service's image (environment/docker-compose.yaml builds it): the base image and the task tooling
# (rcb_robowits.py blenderkit-serve) from the pinned files-only image, at the path the service runs it from.
FROM ghcr.io/mll-lab-nu/efe:robowits-0.1.1
COPY --from=ghcr.io/mll-lab-nu/efe:robowits-files-0.8.0@sha256:763b7fc62cab021d13b3d5c4f3533e2a68498484687125dd08221873a5d343ef /privileged/tests/rcb_robowits.py /srv/rcb_robowits.py
