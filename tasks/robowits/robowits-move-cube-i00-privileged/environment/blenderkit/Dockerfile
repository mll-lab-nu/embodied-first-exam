# The `blenderkit` service's image (environment/docker-compose.yaml builds it): the base image and the task tooling
# (rcb_robowits.py blenderkit-serve) from the pinned files-only image, at the path the service runs it from.
FROM ghcr.io/mll-lab-nu/efe:robowits-0.1.1
COPY --from=ghcr.io/mll-lab-nu/efe:robowits-files-0.7.0@sha256:1a8331706da528df73308861c637fc08344f86ac9090c43141455df6e7c86df8 /privileged/tests/rcb_robowits.py /srv/rcb_robowits.py
