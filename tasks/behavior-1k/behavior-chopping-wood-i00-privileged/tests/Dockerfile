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
# Separate verifier sandbox (PROTOCOL §4): the same simulator image with the verifier's own copies of the
# tooling, the robot config and the frozen instance baked in (the grader, the tooling and the robot config from the
# files-only image eai-behavior-files, pinned by digest). Nothing the agent did in its container reaches this
# one — Harbor uploads only the declared artifacts (/app/output/), so a patched success check or a swapped
# interpreter in the agent container cannot influence the verdict.
FROM behavior-base
COPY instance.json test.sh /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:behavior-files-0.2.1@sha256:9d94348fe2d0f8944b12c4e85206be77e0da5cde24d070e82309c780e9b803d0 /privileged/grade.py /tests/grade.py
COPY --from=ghcr.io/mll-lab-nu/efe:behavior-files-0.2.1@sha256:9d94348fe2d0f8944b12c4e85206be77e0da5cde24d070e82309c780e9b803d0 /rcb_behavior.py /tests/rcb_behavior.py
COPY --from=ghcr.io/mll-lab-nu/efe:behavior-files-0.2.1@sha256:9d94348fe2d0f8944b12c4e85206be77e0da5cde24d070e82309c780e9b803d0 /r1pro_primitives_eval.yaml /tests/r1pro_primitives_eval.yaml
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
# this task's state-dump patch (sitecustomize.py, imported at startup from PYTHONPATH): the state can be dumped on the
# step a log is split; the shared tooling is unchanged
COPY sitecustomize.py /tests/sitecustomize.py
ENV PYTHONHASHSEED=0
WORKDIR /tests
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.2.0@sha256:65442d9e9eeb493d785a59d48a321345e2b48186946cc9d55beb684182514b4b /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
