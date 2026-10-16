# eai-ispatialgym: iSpatialGym "eval v1.0" (kmy17518/iSpatialGym, branch ispatialgym-eval-release) on its BEHAVIOR-1K fork
# (kmy17518/BEHAVIOR-1K, branch ispatialgym-eval: OmniGibson 3.9 + the vector-env merge + iSpatialGym's object states) and
# NVlabs cuRobo v0.8.0, as iSpatialGym's setup.sh installs them, on eai-behavior (Isaac Sim 5.1.0, ffmpeg).
# Runs only in a task's trusted `sim` sidecar: the agent's container is the eai-standard client and never sees this image.
# No dataset: the BEHAVIOR Data Bundle (licence: no redistribution) is mounted read-only from $RCB_BEHAVIOR_DATA at /bdata; the
# image holds only iSpatialGym's own small dataset `ispatialgym-assets` (its Kohs block, tray, puzzle pieces and mock-up).
# BUILD_ONLY (NVIDIA Isaac Sim inside; images/ispatialgym/BUILD_ONLY). Build eai-behavior first, then from the repo root:
#   docker build --build-context ispatialgym=<a clean checkout of iSpatialGym at ISG_COMMIT> \
#     -t ghcr.io/mll-lab-nu/eai-ispatialgym:$(cat images/ispatialgym/VERSION) -f images/ispatialgym/Dockerfile .
FROM ghcr.io/mll-lab-nu/eai-behavior:0.1.1
ARG B1K_COMMIT=6a6194600939179671054e1ae5e78b0a158f996c
ARG ISG_COMMIT=6c1ed2e7ead746129a7aa4648618f9f6063e1ec3
ARG ISG_TREE_SHA256=35670cc7631013beff505c0a35de99c747ada151cd2c901c4755788c90da765f
ARG CUROBO_COMMIT=4ea77366ca48ee453e7df139e39fa6532af49f3b
# OmniGibson and bddl are editable installs of /behavior-src in the official image: the fork's checkout replaces it
RUN rm -rf /behavior-src && git init -q /behavior-src && cd /behavior-src && \
    git fetch -q --depth 1 https://github.com/kmy17518/BEHAVIOR-1K.git ${B1K_COMMIT} && git checkout -q FETCH_HEAD && rm -rf .git && \
    pip install --no-cache-dir --no-deps -e /behavior-src/OmniGibson -e /behavior-src/bddl3
# cuRoboV2 in place of BEHAVIOR's cuRobo v1 fork (iSpatialGym's setup.sh --primitives, its pins): built without isolation so
# that its package data (curobo/content) is installed; then packaging < 26 again (lerobot's range) and pillow ~= 11.0;
# constraints.txt fixes every version the install adds or changes
RUN --mount=type=bind,source=images/ispatialgym/constraints.txt,target=/tmp/constraints.txt \
    export PIP_CONSTRAINT=/tmp/constraints.txt && pip uninstall -y nvidia_curobo && \
    SETUPTOOLS_SCM_PRETEND_VERSION_FOR_NVIDIA_CUROBO=0.8.0 pip install --no-cache-dir --no-build-isolation \
        "nvidia-curobo[cu12] @ git+https://github.com/NVlabs/curobo@${CUROBO_COMMIT}" && \
    pip install --no-cache-dir "packaging==25.0" "pillow==11.0.0" && \
    python -c "import os, curobo; assert os.path.exists(os.path.join(os.path.dirname(curobo.__file__), 'content', 'configs', 'task', 'ik', 'lbfgs_ik.yml'))"
# iSpatialGym itself (editable, as its setup.sh installs it: the BDDL domain and problems stay under ispatialgym/assets).
# The repository is private, so the builder passes a clean checkout of the pinned commit as the build context `ispatialgym`
# (images/ispatialgym/BUILD_ONLY); the build refuses any other tree (the hash of every file but .git/, by path and content).
RUN --mount=type=bind,from=ispatialgym,target=/isg \
    mkdir -p /opt/ispatialgym && tar -C /isg --exclude=./.git -cf - . | tar -C /opt/ispatialgym -xf - && \
    cd /opt/ispatialgym && test "$(find . -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)" = "${ISG_TREE_SHA256}" && \
    pip install --no-cache-dir --no-deps -e /opt/ispatialgym && \
    mkdir -p /data && cp -r /opt/ispatialgym/ispatialgym/assets/datasets/ispatialgym-assets /data/ispatialgym-assets && \
    python -c "import ispatialgym, ispatialgym.sampling"
# the licensed dataset: a task mounts $RCB_BEHAVIOR_DATA whole at /bdata (read-only); OmniGibson reads its parts at /data,
# next to the image's own ispatialgym-assets
RUN ln -s /bdata/behavior-1k-assets /data/behavior-1k-assets && ln -s /bdata/omnigibson-robot-assets /data/omnigibson-robot-assets && \
    ln -s /bdata/omnigibson.key /data/omnigibson.key
# the settings iSpatialGym's eval demos and goal images were recorded with (its README); OmniGibson reads /data
ENV OMNI_KIT_ACCEPT_EULA=YES HDF5_USE_FILE_LOCKING=FALSE HF_HUB_OFFLINE=1 \
    OMNIGIBSON_TRACK_STATE_UPDATES=1 OMNIGIBSON_CHANGE_DETECTION_NUMPY=1 OMP_NUM_THREADS=1 NUMPY_MADVISE_HUGEPAGE=0 \
    ISPATIALGYM_CUROBO_WARMUP_ITERS=0 PYTHONHASHSEED=0
