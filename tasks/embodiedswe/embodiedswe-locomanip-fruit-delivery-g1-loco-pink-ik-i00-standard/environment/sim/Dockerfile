# The `sim` sidecar: EmbodiedSWE's base image (images/embodiedswe/, built locally: BUILD_ONLY), this directory at /srv
# (the task's instance, grader and text), and at their paths under /srv the shared files, from pinned files-only images.
FROM ghcr.io/mll-lab-nu/efe-private:embodiedswe-0.3.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodiedswe-files-0.3.1@sha256:ef309a60a26d8813914d4c5284eb9a1008d58f3123871491535f7cf11bbc743e \
     /rcb_embodiedswe.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodiedswe-standard-files-0.5.0@sha256:3ff868b687661b80246f36ee3425ec4d229f88f8c090acdcb4a813e59408349b \
     /sim/esw_std.py \
     /sim/finalize.sh \
     /sim/live_video.py \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:8a712f54d69d3fb089573d962c0756ef1026119a4337be28785e4a14410d20b3 \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:agent-end-files-0.5.0@sha256:b6943584134a0cabb6d0a42a7a4e5e617be92c7299468e90a6021a023b6e557e /rcb_agent_end.py /srv/rcb_agent_end.py
