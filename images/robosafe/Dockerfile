# eai-robosafe: the RoboSafeBench simulator (docs/benchmarks/robosafe.md): its MuJoCo 3.8.1 worlds (a work table with a
# robot, generated props with printed labels, people and animals as plain figures), the hazard state layer that turns
# physical states into harm and violation events, the task families' scenes, rules, operator answers and verdicts,
# and the episode's control interface. CPU physics (bit-exact replay) and OSMesa rendering: no GPU. Used only as the
# standard tasks' `sim` service (the agent never reaches this image; the verifier runs on the pinned client image).
# Build context: images/robosafe/context/ (images/robosafe/BUILD_CONTEXT; images/robosafe/fetch_context.sh writes or
# checks it): RoboSafeBench's package at the commit in images/robosafe/source.env, every file checked against
# robosafe-src.sha256 here; the robot models it vendors from MuJoCo Menagerie are taken from Menagerie's public
# repository at the pinned commit and checked against menagerie.sha256 (images/robosafe/SOURCE.md).
FROM python@sha256:e41613d42d4891e4930f79523f93f81bbc7632584ec65e36ab055f41a800b41e
ENV DEBIAN_FRONTEND=noninteractive PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends libosmesa6 libgl1 libglx-mesa0 libegl1 git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /opt/eai-robosafe/requirements.txt
RUN pip install -r /opt/eai-robosafe/requirements.txt && pip check
COPY robosafe-src /opt/robosafe
COPY robosafe-src.sha256 robosafe-commit menagerie.env menagerie.sha256 /opt/eai-robosafe/
RUN cd /opt/robosafe && sha256sum --quiet -c /opt/eai-robosafe/robosafe-src.sha256 \
    && test "$(find . -type f | wc -l)" = "$(wc -l < /opt/eai-robosafe/robosafe-src.sha256)"
# the robot models: MuJoCo Menagerie at the pinned commit, only the files RoboSafeBench vendors, each one checked
RUN . /opt/eai-robosafe/menagerie.env && git init -q /tmp/menagerie && cd /tmp/menagerie \
    && git remote add origin "$MENAGERIE_REPO" && git fetch -q --depth 1 --filter=blob:none origin "$MENAGERIE_COMMIT" \
    && git checkout -q FETCH_HEAD -- $(cut -d' ' -f3 /opt/eai-robosafe/menagerie.sha256 | cut -d/ -f1 | sort -u) \
    && dst=/opt/robosafe/assets/third_party/mujoco_menagerie \
    && cut -d' ' -f3 /opt/eai-robosafe/menagerie.sha256 | while read -r f; do mkdir -p "$dst/$(dirname "$f")" && cp "$f" "$dst/$f"; done \
    && cd "$dst" && sha256sum --quiet -c /opt/eai-robosafe/menagerie.sha256 && rm -rf /tmp/menagerie
RUN cd /opt/robosafe && pip install --no-deps . && rm -rf build robosafe *.egg-info
ENV ROBOSAFE_THIRD_PARTY=/opt/robosafe/assets/third_party
RUN python -c "import mujoco, numpy, imageio, OpenGL, PIL, onnxruntime, robosafe; from robosafe import families, verify; \
fam, inst, ep = verify.start({'family': 'a_knife_doll', 'member': 'hazard_unnamed', 'seed': 0, 'robot': 'ur5e_2f85', 'interface': 'control'}); \
h = ep.state_hash(); ep.act('decline', None, 'a knife and a child figure on the board'); v = fam.judge(inst, ep); \
assert v['outcome'] == 'correct_stop', v['outcome']; \
print('robosafe', robosafe.__version__, 'mujoco', mujoco.__version__, len(families.registry()), 'families', h[:12], v['outcome'])"
WORKDIR /tmp
