# The `sim` sidecar's image (environment/docker-compose.yaml builds it): images/behavior/Dockerfile, verbatim.
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
