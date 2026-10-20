# >>> images/behavior/Dockerfile
# behavior: BEHAVIOR-1K v3.9.2 (OmniGibson 3.9.2 + Isaac Sim 5.1.0 + cuRobo, the version the 2026 BEHAVIOR Challenge pins):
# the official image by digest + ffmpeg, from public sources only. Every BEHAVIOR-1K task Dockerfile that runs the
# simulator holds this recipe verbatim (normalize_base_stages) and its compose service names our prebuilt copy,
# ghcr.io/mll-lab-nu/efe-private:behavior-<VERSION>, as `build.cache_from`: with access Docker reuses its layers, without
# access it builds these steps itself. iSpatialGym's recipe starts with this one. No dataset: the BEHAVIOR Data Bundle licence forbids
# redistribution; a task mounts the user's licensed copy read-only from $RCB_BEHAVIOR_DATA (tasks/behavior-1k/README.md).
# FIXED versions (README.md here): the base by digest; ffmpeg and every dependency from the Ubuntu archive snapshot of
# 2026-09-20, and the build fails unless the package state is dpkg.lock's (the tested image's dpkg-query list; the build
# compares its sha256, so it needs no file from this repository).
FROM docker.io/stanfordvl/behavior:3.9.2@sha256:2702900192741904e69a573aa7869ea51c592586f9791050796efc37faa893fb AS behavior-base
# Harbor runs the agent and the verifier with `docker exec`, which bypasses /entrypoint.sh (conda activate), so put
# the `behavior` env first on PATH. Headless + data/cache locations match the official run_docker.sh conventions.
ENV PATH=/opt/conda/envs/behavior/bin:${PATH} \
    OMNIGIBSON_HEADLESS=1 \
    OMNIGIBSON_DATA_PATH=/data \
    OMNIGIBSON_APPDATA_PATH=/cache/appdata \
    PYTHONUNBUFFERED=1
# snapshot.ubuntu.com is slow and sometimes answers 503: apt retries each file with backoff instead of failing the build
RUN apt-get -o Acquire::Retries=10 update --snapshot 20260920T090000Z && \
    apt-get -o Acquire::Retries=10 install --snapshot 20260920T090000Z -y --no-install-recommends ffmpeg=7:6.1.1-3ubuntu5 && \
    dpkg-query -W -f='${db:Status-Status} ${Package}:${Architecture} ${Version}\n' | LC_ALL=C sort > /tmp/dpkg.state && \
    { echo "99b494070459b5784b7be12d6b5578018a0cba839fb4fca7236bc506bf28d520  /tmp/dpkg.state" | sha256sum -c - || \
      { echo "package state differs from images/behavior/dpkg.lock (the tested image):" >&2; cat /tmp/dpkg.state >&2; exit 1; }; } && \
    rm -rf /var/lib/apt/lists/* /tmp/dpkg.state && mkdir -p /app/output /cache/appdata /data
WORKDIR /app
# <<< images/behavior/Dockerfile
# The task's image: behavior-base (the recipe above, BEHAVIOR-1K v3.9.2) + everything task-specific; the tooling comes
# from the files-only image eai-behavior-files (images/behavior-files/, pinned by digest). The BEHAVIOR dataset is NOT in any image (its license forbids redistribution):
# environment/docker-compose.yaml mounts the host's licensed copy.
FROM behavior-base
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
