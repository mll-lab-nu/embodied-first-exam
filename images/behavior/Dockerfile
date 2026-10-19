# behavior: BEHAVIOR-1K v3.9.2 (OmniGibson 3.9.2 + Isaac Sim 5.1.0 + cuRobo), the version pinned by the 2026
# BEHAVIOR Challenge. Built on the official image; infrastructure only, contains no benchmark code.
#
# It also contains NO dataset: the BEHAVIOR Data Bundle license forbids redistributing the encrypted assets or the
# decryption key, and the official image ships without them too. Each host downloads its own licensed copy (see
# docs) and a task mounts it read-only at /data through its environment/docker-compose.yaml, which is also where the
# task reserves a GPU: Isaac Sim needs an RTX-class NVIDIA GPU even when headless. Tag = images/behavior/VERSION.
# BUILD_ONLY (never pushed: NVIDIA Isaac Sim inside). Build from the repo root, as images/behavior/BUILD_ONLY says:
#   docker build -t ghcr.io/mll-lab-nu/efe-private:behavior-$(cat images/behavior/VERSION) -f images/behavior/Dockerfile .
#
# FIXED versions (README.md here): the base by digest, and ffmpeg with every dependency at the versions of the tested image
# (built 2026-09-20): apt reads the Ubuntu archive snapshot of that day, and the build fails unless the resulting package
# state equals dpkg.lock (the tested image's dpkg-query list).
FROM stanfordvl/behavior:3.9.2@sha256:2702900192741904e69a573aa7869ea51c592586f9791050796efc37faa893fb
# Harbor runs the agent and the verifier with `docker exec`, which bypasses /entrypoint.sh (conda activate), so put
# the `behavior` env first on PATH. Headless + data/cache locations match the official run_docker.sh conventions.
ENV PATH=/opt/conda/envs/behavior/bin:${PATH} \
    OMNIGIBSON_HEADLESS=1 \
    OMNIGIBSON_DATA_PATH=/data \
    OMNIGIBSON_APPDATA_PATH=/cache/appdata \
    PYTHONUNBUFFERED=1
# snapshot.ubuntu.com is slow and sometimes answers 503: apt retries each file with backoff instead of failing the build
RUN --mount=type=bind,source=images/behavior/dpkg.lock,target=/tmp/dpkg.lock \
    apt-get -o Acquire::Retries=10 update --snapshot 20260920T090000Z && \
    apt-get -o Acquire::Retries=10 install --snapshot 20260920T090000Z -y --no-install-recommends ffmpeg=7:6.1.1-3ubuntu5 && \
    dpkg-query -W -f='${db:Status-Status} ${Package}:${Architecture} ${Version}\n' | LC_ALL=C sort | diff - /tmp/dpkg.lock && \
    rm -rf /var/lib/apt/lists/* && mkdir -p /app/output /cache/appdata /data
WORKDIR /app
