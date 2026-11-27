# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:ikea-mujoco-sim-0.4.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:ikea-mujoco-files-0.8.0@sha256:a4231b93ed125d76abe0e5630c2ed1877b25678878c338c0a608594cf54eda06 \
     /sim/finalize.sh \
     /sim/ikea_nyx.py \
     /sim/ikea_rig.py \
     /privileged/environment/rcb_ikea.py \
     /sim/rig.json \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:roboarc-files-0.8.0@sha256:906e6db4747259bf83aa9454b720765d155ff2c6b578ed06b815c8ef3146896e /nyx_direct.py /srv/nyx_direct.py
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:497a2b864b3a1aaf1f60206dc14f08a0f99960037f0e54be3d4bc2e39f5adba4 \
     /rcb1.py \
     /operations/rcb_limited.py \
     /run.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:497a2b864b3a1aaf1f60206dc14f08a0f99960037f0e54be3d4bc2e39f5adba4 /agent_end/rcb_agent_end.py /srv/rcb_agent_end.py
