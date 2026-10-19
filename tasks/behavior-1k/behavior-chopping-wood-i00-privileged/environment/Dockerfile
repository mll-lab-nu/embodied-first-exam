# Base image = BEHAVIOR-1K v3.9.2 (images/behavior/: BUILD_ONLY, every host builds it). Everything task-specific is
# copied here; the tooling comes from the files-only image eai-behavior-files (images/behavior-files/, pinned by digest;
# BUILD_ONLY). The BEHAVIOR dataset is NOT in any image (its license forbids redistribution):
# environment/docker-compose.yaml mounts the host's licensed copy.
FROM ghcr.io/mll-lab-nu/efe-private:behavior-0.1.1
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:behavior-files-0.2.0@sha256:e2594de8dd89711e917968ab5dc01d13f614f6e9844f05263ae67736109f3f85 /rcb_behavior.py /opt/tools/rcb_behavior.py
COPY --from=ghcr.io/mll-lab-nu/efe:behavior-files-0.2.0@sha256:e2594de8dd89711e917968ab5dc01d13f614f6e9844f05263ae67736109f3f85 /r1pro_primitives_eval.yaml /opt/tools/r1pro_primitives_eval.yaml
ENV PYTHONPATH=/opt/tools
# this task's state-dump patch (sitecustomize.py, imported at startup from PYTHONPATH): the state can be dumped on the
# step a log is split (board 0178); the shared tooling is unchanged
COPY sitecustomize.py /opt/tools/sitecustomize.py
# sets of strings iterate in the same order in every process (with the tooling's stable object hashes, item 16 of the
# 2026-10-14 failure analysis: a replay must take the same path as the live run)
ENV PYTHONHASHSEED=0
RUN mkdir -p /app/output
WORKDIR /app
