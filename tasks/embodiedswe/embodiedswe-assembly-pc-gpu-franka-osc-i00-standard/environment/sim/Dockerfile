# The `sim` sidecar: EmbodiedSWE's base image (images/embodiedswe/, built locally: BUILD_ONLY), this directory at /srv
# (the task's instance, grader and text), and at their paths under /srv the shared files, from pinned files-only images.
FROM ghcr.io/mll-lab-nu/efe-private:embodiedswe-0.3.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodiedswe-files-0.3.1@sha256:ef309a60a26d8813914d4c5284eb9a1008d58f3123871491535f7cf11bbc743e \
     /rcb_embodiedswe.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodiedswe-standard-files-0.3.0@sha256:e2a90a2531e4d3f8c66601760b1d1619b234a077c698a036c12694adcd86f3a1 \
     /sim/esw_std.py \
     /sim/finalize.sh \
     /sim/live_video.py \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.5.0@sha256:a6c2ac2ede9fe2c1744f9c6e67c6a49de9c5a8b8c2c9ae4f0d774b7dd72662ff \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:agent-end-files-0.1.1@sha256:af4fa3c2f87c31e67f03232d39ef54d82a0e06d57c23da1c56cd69936779b6d9 /rcb_agent_end.py /srv/rcb_agent_end.py
