# >>> images/vlabench/Dockerfile
# vlabench: VLABench (OpenMOSS/VLABench @ cf588fe) on MuJoCo 3.2.2 / dm_control 1.0.22 with its pinned assets
# (lerobot/vlabench-assets @ 08d7a44, ~12 GB); CPU physics (bit-exact replay) and CPU rendering (OSMesa): no GPU.
# One image for the VLABench privileged tasks' environment and verifier and the standard tasks' `sim` service.
# Deliberately NOT included: VLABench's reference solutions (strip_experts.py, last layers).
# Built from public sources only, with no build context: Debian packages from a dated snapshot, this directory's
# requirements.txt and strip_experts.py from the public files-only image efe:vlabench-build-files. Every VLABench task's
# Dockerfiles start with this file (stage vlabench-base) and name efe-private:vlabench-<VERSION> as their build cache:
# a runner that can pull it takes its layers, any other runner builds them here (tasks/vlabench/README.md).
FROM docker.io/library/python:3.10.18-slim-bookworm@sha256:445b9efb2c047a7ccdb30d293fd6b1aa0f62a55062dc2b69051df91e10848749 AS vlabench-base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
# Debian packages as of the snapshot (the image's apt sources are restored afterwards).
RUN cp /etc/apt/sources.list.d/debian.sources /tmp/debian.sources \
    && sed -i 's|http://deb.debian.org/debian-security|http://snapshot.debian.org/archive/debian-security/20261002T000000Z|; s|http://deb.debian.org/debian$|http://snapshot.debian.org/archive/debian/20261002T000000Z|' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Check-Valid-Until=false update && apt-get install -y --no-install-recommends \
    git git-lfs libosmesa6 libgl1 libglib2.0-0 libgomp1 ffmpeg \
    && mv /tmp/debian.sources /etc/apt/sources.list.d/debian.sources && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/mll-lab-nu/efe:vlabench-build-files-0.1.0@sha256:ccdaaf2d32c7010013f6c33444452015d252d8cafc2cc39470bb6307fdc7655d /requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && pip check
RUN git clone https://github.com/OpenMOSS/VLABench.git /opt/VLABench \
    && cd /opt/VLABench && git checkout cf588fe60c0c7282174fe979f5913170cfe69017
RUN git clone https://github.com/motion-planning/rrt-algorithms.git /opt/rrt-algorithms \
    && cd /opt/rrt-algorithms && git checkout 14e47963780affe3ff3bb9fc33a4b14e1a733e85 \
    && pip install --no-deps .
# Upstream RRT subdirectories have no __init__.py; its wheel omits them.
ENV PYTHONPATH=/opt/VLABench:/opt/rrt-algorithms
RUN GIT_LFS_SKIP_SMUDGE=1 git clone https://huggingface.co/datasets/lerobot/vlabench-assets /tmp/assets \
    && cd /tmp/assets && git checkout 08d7a4479a55c8fbb89ac0fd6fcf06e53d65b4a4 \
    && git lfs pull && git lfs fsck \
    && cp -a obj scenes /opt/VLABench/VLABench/assets/ \
    && rm -rf /tmp/assets
RUN printf '%s\n' 'cf588fe60c0c7282174fe979f5913170cfe69017' > /opt/vlabench-commit \
    && printf '%s\n' '08d7a4479a55c8fbb89ac0fd6fcf06e53d65b4a4' > /opt/vlabench-assets-commit
COPY --from=ghcr.io/mll-lab-nu/efe:vlabench-build-files-0.1.0@sha256:ccdaaf2d32c7010013f6c33444452015d252d8cafc2cc39470bb6307fdc7655d /strip_experts.py /tmp/strip_experts.py
RUN python /tmp/strip_experts.py /opt/VLABench/VLABench \
    && rm -rf /opt/VLABench/.git /opt/VLABench/scripts /tmp/strip_experts.py \
    && python -c "import importlib.util as u; assert u.find_spec('VLABench.evaluation') is None"
ENV VLABENCH_ROOT=/opt/VLABench/VLABench
WORKDIR /app
# <<< images/vlabench/Dockerfile
# Separate verifier sandbox: the same VLABench image (stage vlabench-base above) with the verifier's own copies of the tooling and the frozen instance;
# only the declared artifacts (/app/output/) arrive from the agent.
FROM vlabench-base
COPY test.sh instance.json /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:vlabench-files-0.3.0@sha256:44da3b5283e51867a637439e4ae9503c660eb2d89d3677be488ae5b4501c57c2 /privileged/environment/vlb_tool.py /privileged/tests/grade.py /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests:/opt/VLABench:/opt/rrt-algorithms
WORKDIR /tests
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.3.0@sha256:53154417782408df8309194971b08b18c3682d2b337e2e3b2eb4c88fe025ab85 /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
