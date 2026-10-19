# eai-metaworld: Meta-World v3 (Farama-Foundation/Metaworld @ 59fc34d) on MuJoCo 3.3.0; CPU physics (bit-exact replay)
# and CPU rendering (OSMesa, ~45 ms per 320x240 frame): no GPU. One image for the MetaWorld+ privileged tasks'
# environment and verifier and the standard tasks' `sim` service. Not merged into eai-mujoco (MuJoCo 3.3.7): frozen
# instance hashes depend on the MuJoCo version.
# Deliberately NOT included: Meta-World's scripted expert policies (metaworld/policies/), removed in the layer that
# installs them.
FROM docker.io/library/python:3.11.13-slim-bookworm@sha256:86adf8dbadc3d6e82ee5dd2c74bec2e1c2467cdad47886280501df722372d2e1
ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
COPY requirements.txt /opt/eai-metaworld/requirements.txt
RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends libosmesa6 libgl1 libglib2.0-0 git \
    && pip install --no-cache-dir -r /opt/eai-metaworld/requirements.txt \
    && pip check \
    && rm -rf "$(python -c 'import metaworld, os; print(os.path.dirname(metaworld.__file__))')/policies" \
    && apt-get purge -y -qq git && apt-get autoremove -y -qq && rm -rf /var/lib/apt/lists/*
RUN python -c "import importlib.util as u, metaworld, mujoco; from metaworld.env_dict import ENV_CLS_MAP; \
assert u.find_spec('metaworld.policies') is None; print('mujoco', mujoco.__version__, 'envs', len(ENV_CLS_MAP))"
WORKDIR /app
