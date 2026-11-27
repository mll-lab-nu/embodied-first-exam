# The `sim` sidecar: EmbodiedSWE's base image (images/embodiedswe/, built locally: BUILD_ONLY), this directory at /srv
# (the task's instance, grader and text), and at their paths under /srv the shared files, from pinned files-only images.
FROM ghcr.io/mll-lab-nu/efe-private:embodiedswe-0.3.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodiedswe-files-0.3.1@sha256:ef309a60a26d8813914d4c5284eb9a1008d58f3123871491535f7cf11bbc743e \
     /rcb_embodiedswe.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodiedswe-files-0.3.1@sha256:ef309a60a26d8813914d4c5284eb9a1008d58f3123871491535f7cf11bbc743e \
     /sim/esw_std.py \
     /sim/finalize.sh \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:497a2b864b3a1aaf1f60206dc14f08a0f99960037f0e54be3d4bc2e39f5adba4 /live_video.py /srv/live_video.py
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:497a2b864b3a1aaf1f60206dc14f08a0f99960037f0e54be3d4bc2e39f5adba4 \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:497a2b864b3a1aaf1f60206dc14f08a0f99960037f0e54be3d4bc2e39f5adba4 /agent_end/rcb_agent_end.py /srv/rcb_agent_end.py
