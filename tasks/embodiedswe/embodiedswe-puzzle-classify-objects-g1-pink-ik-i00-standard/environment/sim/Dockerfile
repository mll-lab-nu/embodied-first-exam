# The `sim` sidecar: EmbodiedSWE's base image (images/embodiedswe/, built locally: BUILD_ONLY), this directory at /srv
# (the task's instance, grader and text), and at their paths under /srv the shared files, from pinned files-only images.
FROM ghcr.io/mll-lab-nu/efe-private:embodiedswe-0.3.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodiedswe-files-0.3.1@sha256:ef309a60a26d8813914d4c5284eb9a1008d58f3123871491535f7cf11bbc743e \
     /rcb_embodiedswe.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodiedswe-standard-files-0.3.0@sha256:11b1dd1dda4f0902b216fa2dda15057cb5952edd5851a6adabb419713a15026d \
     /sim/esw_std.py \
     /sim/finalize.sh \
     /sim/live_video.py \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.5.0@sha256:d0f4045938a9683719f71de2342464216b53c49a87711923fb4afd551c081d82 \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:agent-end-files-0.2.0@sha256:85bb0e3d2a49a8c94d1cefa47d8556d96b9d4afa528fd5ea9532cf53cb79a6e6 /rcb_agent_end.py /srv/rcb_agent_end.py
