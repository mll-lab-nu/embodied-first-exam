# eai-ispatialgym: iSpatialGym (kmy17518/iSpatialGym, MIT, its pre-release "v1.0" evaluation pipeline) on its BEHAVIOR-1K
# fork (kmy17518/BEHAVIOR-1K, branch ispatialgym-eval: OmniGibson 3.9 + the vector-env merge + iSpatialGym's object
# states), as iSpatialGym's setup.sh installs them, on eai-behavior (Isaac Sim 5.1.0, ffmpeg).
# No dataset: the BEHAVIOR Data Bundle (licence: no redistribution) is mounted read-only from $RCB_BEHAVIOR_DATA at /bdata;
# the image holds only iSpatialGym's own small dataset `ispatialgym-assets` (its Kohs block, tray and puzzle pieces). The
# tasks' frozen instances come from the eval data in the task directories, never from a download at run time.
# BUILD_ONLY (NVIDIA Isaac Sim inside; images/ispatialgym/BUILD_ONLY). Build eai-behavior first, then from the repo root:
#   docker build -t ghcr.io/mll-lab-nu/efe-private:ispatialgym-$(cat images/ispatialgym/VERSION) -f images/ispatialgym/Dockerfile .
FROM ghcr.io/mll-lab-nu/efe-private:behavior-0.1.1
ARG B1K_COMMIT=6a6194600939179671054e1ae5e78b0a158f996c
ARG ISG_COMMIT=fddcf756c8134bab1358e539f8b6c1f16ad3e1ec
# OmniGibson and bddl are editable installs of /behavior-src in the official image: the fork's checkout replaces it
# (iSpatialGym pins the same commit as its Behavior-1K submodule)
RUN rm -rf /behavior-src && git init -q /behavior-src && cd /behavior-src && \
    git fetch -q --depth 1 https://github.com/kmy17518/BEHAVIOR-1K.git ${B1K_COMMIT} && git checkout -q FETCH_HEAD && rm -rf .git && \
    pip install --no-cache-dir --no-deps -e /behavior-src/OmniGibson -e /behavior-src/bddl3
# setup.sh --omnigibson: the OmniGibson dependencies the official install leaves out (its REPAIR_SPECS), then iSpatialGym
# itself (editable, as setup.sh installs it); constraints.txt fixes every version this adds or changes
RUN --mount=type=bind,source=images/ispatialgym/constraints.txt,target=/tmp/constraints.txt \
    export PIP_CONSTRAINT=/tmp/constraints.txt && \
    pip install --no-cache-dir "warp-lang==1.12.0" "av>=15.0.0,<16.0.0" "datasets>=4.0.0,<5.0.0" "pyarrow<26" \
        "pillow~=11.0.0" "pandas<3" "numpy<2" && \
    git init -q /opt/ispatialgym && cd /opt/ispatialgym && \
    git fetch -q --depth 1 https://github.com/kmy17518/iSpatialGym.git ${ISG_COMMIT} && git checkout -q FETCH_HEAD && \
    rm -rf .git .gitmodules Behavior-1K && \
    pip install --no-cache-dir -e /opt/ispatialgym && \
    mkdir -p /data && cp -r /opt/ispatialgym/ispatialgym/assets/datasets/ispatialgym-assets /data/ispatialgym-assets && \
    python -c "import omnigibson, ispatialgym.run_isg, ispatialgym.eval.loader"
# the licensed dataset: a task mounts $RCB_BEHAVIOR_DATA whole at /bdata (read-only); OmniGibson reads its parts at /data,
# next to the image's own ispatialgym-assets
RUN ln -s /bdata/behavior-1k-assets /data/behavior-1k-assets && ln -s /bdata/omnigibson-robot-assets /data/omnigibson-robot-assets && \
    ln -s /bdata/omnigibson.key /data/omnigibson.key
# configs/eval.yaml's conditions apart from settle-eval (the tasks turn it on): OmniGibson reads /data
ENV OMNI_KIT_ACCEPT_EULA=YES HDF5_USE_FILE_LOCKING=FALSE HF_HUB_OFFLINE=1 \
    OMNIGIBSON_TRACK_STATE_UPDATES=1 OMNIGIBSON_CHANGE_DETECTION_NUMPY=1 OMP_NUM_THREADS=1 NUMPY_MADVISE_HUGEPAGE=0 \
    PYTHONHASHSEED=0
