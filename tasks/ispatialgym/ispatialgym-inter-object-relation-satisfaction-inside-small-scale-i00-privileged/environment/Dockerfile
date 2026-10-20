# >>> images/ispatialgym/Dockerfile
# ispatialgym: images/behavior/Dockerfile verbatim (stage behavior-base), then iSpatialGym (kmy17518/iSpatialGym, MIT, its
# pre-release "v1.0" evaluation pipeline) on its BEHAVIOR-1K fork (kmy17518/BEHAVIOR-1K, branch ispatialgym-eval: OmniGibson
# 3.9 + the vector-env merge + iSpatialGym's object states), as iSpatialGym's setup.sh installs them, on behavior-base. From
# public sources only. Every iSpatialGym task Dockerfile that runs the simulator holds this recipe verbatim
# (normalize_base_stages) and its compose service names our prebuilt copy, ghcr.io/mll-lab-nu/efe-private:ispatialgym-<VERSION>,
# as `build.cache_from`: with access Docker reuses its layers, without access it builds these steps itself.
# No dataset: the BEHAVIOR Data Bundle (licence: no redistribution) is mounted read-only from $RCB_BEHAVIOR_DATA at /bdata;
# the image holds only iSpatialGym's own small dataset `ispatialgym-assets` (its Kohs block, tray and puzzle pieces). The
# tasks' frozen instances come from the eval data in the task directories, never from a download at run time.
# ---- images/behavior/Dockerfile, verbatim:
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
# ---- iSpatialGym on it:
FROM behavior-base AS ispatialgym-base
ARG B1K_COMMIT=6a6194600939179671054e1ae5e78b0a158f996c
ARG ISG_COMMIT=fddcf756c8134bab1358e539f8b6c1f16ad3e1ec
# OmniGibson and bddl are editable installs of /behavior-src in the official image: the fork's checkout replaces it
# (iSpatialGym pins the same commit as its Behavior-1K submodule)
RUN rm -rf /behavior-src && git init -q /behavior-src && cd /behavior-src && \
    git fetch -q --depth 1 https://github.com/kmy17518/BEHAVIOR-1K.git ${B1K_COMMIT} && git checkout -q FETCH_HEAD && rm -rf .git && \
    pip install --no-cache-dir --no-deps -e /behavior-src/OmniGibson -e /behavior-src/bddl3
# setup.sh --omnigibson: the OmniGibson dependencies the official install leaves out (its REPAIR_SPECS), then iSpatialGym
# itself (editable, as setup.sh installs it). The constraints fix every version this adds or changes on behavior-base
# (from the first build's pip freeze), and the build fails unless the resulting `pip list` is the tested image's (sha256).
RUN printf '%s\n' pillow==11.0.0 warp-lang==1.12.0 > /tmp/constraints.txt && export PIP_CONSTRAINT=/tmp/constraints.txt && \
    pip install --no-cache-dir "warp-lang==1.12.0" "av>=15.0.0,<16.0.0" "datasets>=4.0.0,<5.0.0" "pyarrow<26" \
        "pillow~=11.0.0" "pandas<3" "numpy<2" && \
    git init -q /opt/ispatialgym && cd /opt/ispatialgym && \
    git fetch -q --depth 1 https://github.com/kmy17518/iSpatialGym.git ${ISG_COMMIT} && git checkout -q FETCH_HEAD && \
    rm -rf .git .gitmodules Behavior-1K && \
    pip install --no-cache-dir -e /opt/ispatialgym && \
    mkdir -p /data && cp -r /opt/ispatialgym/ispatialgym/assets/datasets/ispatialgym-assets /data/ispatialgym-assets && \
    python -c "import omnigibson, ispatialgym.run_isg, ispatialgym.eval.loader" && \
    python -m pip list --format=freeze 2>/dev/null | LC_ALL=C sort > /tmp/pip.state && \
    { echo "2c9f1fb29308dbec2d5c523006d5d4ef7e03b2fc83f600940872ac12f9be35c4  /tmp/pip.state" | sha256sum -c - || \
      { echo "pip packages differ from the tested image's:" >&2; cat /tmp/pip.state >&2; exit 1; }; } && \
    rm /tmp/constraints.txt /tmp/pip.state
# the licensed dataset: a task mounts $RCB_BEHAVIOR_DATA whole at /bdata (read-only); OmniGibson reads its parts at /data,
# next to the image's own ispatialgym-assets
RUN ln -s /bdata/behavior-1k-assets /data/behavior-1k-assets && ln -s /bdata/omnigibson-robot-assets /data/omnigibson-robot-assets && \
    ln -s /bdata/omnigibson.key /data/omnigibson.key
# configs/eval.yaml's conditions apart from settle-eval (the tasks turn it on): OmniGibson reads /data
ENV OMNI_KIT_ACCEPT_EULA=YES HDF5_USE_FILE_LOCKING=FALSE HF_HUB_OFFLINE=1 \
    OMNIGIBSON_TRACK_STATE_UPDATES=1 OMNIGIBSON_CHANGE_DETECTION_NUMPY=1 OMP_NUM_THREADS=1 NUMPY_MADVISE_HUGEPAGE=0 \
    PYTHONHASHSEED=0
# <<< images/ispatialgym/Dockerfile
# Privileged mode: the agent and the simulator share this container (docs/protocol/README.md §3). eai-ispatialgym, with a layer
# that removes what states or solves a task and asserts nothing of it is left (scrub.sh, bind-mounted for the build only),
# and this task's frozen start (instance.json, the copy the standard twin and the verifier also hold): no goal, no target,
# no success check here; the verifier has them (tests/).
FROM ispatialgym-base
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:ispatialgym-goals-files-0.1.0@sha256:a5b14edb2270793a3d97edeb2ff151646532f30221fe40b55867d33732c97e7f /inter-object-relation-satisfaction-inside-small-scale-i00/goal.png /app/goal.png
COPY --from=ghcr.io/mll-lab-nu/efe:ispatialgym-files-0.2.0@sha256:f07933a4ac0bab0b0743f4754d67587798e70e47c10057c44827a94d6cbb8ea9 /privileged/environment/rcb_ispatialgym.py /opt/tools/rcb_ispatialgym.py
RUN --mount=type=bind,source=scrub,target=/tmp/scrub sh /tmp/scrub/scrub.sh \
      /opt/ispatialgym/ispatialgym/assets/bddl/activity_definitions/inter_object_relation_satisfaction/problem0.bddl && mkdir -p /app/output
ENV PYTHONPATH=/opt/tools OMNIGIBSON_HEADLESS=1
WORKDIR /app
