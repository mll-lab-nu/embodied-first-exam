# The `sim` sidecar: EmbodiedSWE's base image (images/embodiedswe/, built locally: BUILD_ONLY), this directory at /srv
# (the task's instance, grader and text), and at their paths under /srv the shared files, from pinned files-only images.
FROM ghcr.io/mll-lab-nu/efe-private:embodiedswe-0.3.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodiedswe-files-0.4.0@sha256:39e678fbc46858843efd77c27fd11fe57d6bd768af11e0c6ce37ad3a84f52351 \
     /rcb_embodiedswe.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodiedswe-files-0.4.0@sha256:39e678fbc46858843efd77c27fd11fe57d6bd768af11e0c6ce37ad3a84f52351 \
     /sim/esw_std.py \
     /sim/finalize.sh \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:6bf677373ff69d440d4640253caed50067929b8bf4a5d3a9c5f7315cd2752470 /live_video.py /srv/live_video.py
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:6bf677373ff69d440d4640253caed50067929b8bf4a5d3a9c5f7315cd2752470 \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:6bf677373ff69d440d4640253caed50067929b8bf4a5d3a9c5f7315cd2752470 /agent_end/rcb_agent_end.py /srv/rcb_agent_end.py
