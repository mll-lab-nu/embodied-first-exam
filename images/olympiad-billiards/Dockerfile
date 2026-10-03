# eai-olympiad-billiards: the Embodied Agent Olympiad's billiards simulator stack: pooltool 0.6.0 (event-based billiards
# physics, numba JIT on CPU; panda3d is a pooltool dependency, never used for rendering), a PIL renderer's fonts and
# ffmpeg for the replay video. Same pinned Python base as eai-olympiad. The task mounts its code at /srv
# (docker-compose: ./sim:/srv:ro). Build locally: docker build -t ghcr.io/mll-lab-nu/eai-olympiad-billiards:$(cat VERSION) .
FROM docker.io/library/python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7
ENV DEBIAN_FRONTEND=noninteractive PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
COPY requirements.txt /opt/eai-olympiad-billiards/requirements.txt
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends fonts-dejavu-core \
    && pip install --extra-index-url https://archive.panda3d.org/ -r /opt/eai-olympiad-billiards/requirements.txt \
    && rm -rf /var/lib/apt/lists/*
# compile pooltool's numba kernels into its on-disk cache once, at build time (a shot with spin, continuized)
RUN PYTHONDONTWRITEBYTECODE= python -c "import pooltool as pt; \
s = pt.System(cue=pt.Cue(cue_ball_id='cue'), table=pt.Table.default(), \
              balls={'cue': pt.Ball.create('cue', xy=(0.3, 0.3)), '1': pt.Ball.create('1', xy=(0.5, 0.9))}); \
s.cue.set_state(V0=2.0, phi=80.0, theta=0.0, a=0.1, b=-0.2); pt.simulate(s, inplace=True, max_events=5000); \
pt.continuize(s, dt=1/30, inplace=True); print('pooltool', pt.__version__ if hasattr(pt, '__version__') else '0.6.0')"
WORKDIR /srv
