# The `sim` sidecar: EmbodiedSWE's base image (images/embodiedswe/, built locally: BUILD_ONLY), this directory at /srv
# (the task's instance, grader and text), and at their paths under /srv the shared files, from pinned files-only images.
FROM ghcr.io/mll-lab-nu/efe-private:embodiedswe-0.3.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodiedswe-files-0.3.1@sha256:ef309a60a26d8813914d4c5284eb9a1008d58f3123871491535f7cf11bbc743e \
     /rcb_embodiedswe.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodiedswe-standard-files-0.2.0-stateq-resetinf-pose@sha256:132d6f9e940bdf72aa650c82d5c9fca6cb444fe19a9ea715e6e07438d4eb6b3f \
     /sim/esw_std.py \
     /sim/finalize.sh \
     /sim/live_video.py \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.0-stateq@sha256:07fbf9e22ea11efd3398ef74d888ee7544410c1e07ff49e3fc5b8606b9acfe38 \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
