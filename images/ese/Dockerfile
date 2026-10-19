# ese: the Embodied Safety Exam simulator (docs/benchmarks/embodied-safety-exam.md): its MuJoCo 3.8.1 worlds (a work table with a
# robot, generated props with printed labels, people and animals as plain figures), the hazard state layer that turns
# physical states into harm and violation events, the task families' scenes, rules, operator answers and verdicts,
# and the episode's control interface. CPU physics (bit-exact replay) and OSMesa rendering: no GPU. Used only as the
# standard tasks' `sim` service (the agent never reaches this image; the verifier runs on the pinned client image).
# Build context: images/ese/context/ (images/ese/BUILD_CONTEXT; images/ese/fetch_context.sh writes or
# checks it): Embodied Safety Exam's package at the commit in images/ese/source.env, every file checked against
# ese-src.sha256 here; the robot models it vendors from MuJoCo Menagerie are taken from Menagerie's public
# repository at the pinned commit and checked against menagerie.sha256 (images/ese/SOURCE.md).
# Before building, `python3 images/ese/assets.py fetch` puts the realism_v3 textures and meshes (kept out of git, in
# the Hugging Face dataset pinned in images/ese/assets.json) into the context; without them the check below fails.
FROM docker.io/library/python@sha256:0a310eeecf4e1f5a0743f9a6520c90c88d089c903ca5fd283f501e3a805f5f89 AS dependencies
ENV DEBIAN_FRONTEND=noninteractive PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
RUN apt-get -o APT::Sandbox::User=root update -qq && apt-get -o APT::Sandbox::User=root install -y -qq --no-install-recommends libosmesa6 libgl1 libglx-mesa0 libegl1 git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /opt/ese-image/requirements.txt
RUN pip install -r /opt/ese-image/requirements.txt && pip check
FROM dependencies AS final
COPY ese-src /opt/ese
COPY ese-src.sha256 ese-commit menagerie.env menagerie.sha256 /opt/ese-image/
COPY third_party_context.py third-party-duplicates.json /opt/ese-image/
RUN cd /opt/ese && sha256sum --quiet -c /opt/ese-image/ese-src.sha256 \
    && test "$(find . -type f | wc -l)" = "$(wc -l < /opt/ese-image/ese-src.sha256)"
# the robot models: MuJoCo Menagerie at the pinned commit, only the files Embodied Safety Exam vendors, each one checked
RUN . /opt/ese-image/menagerie.env && git init -q /tmp/menagerie && cd /tmp/menagerie \
    && git remote add origin "$MENAGERIE_REPO" && git fetch -q --depth 1 --filter=blob:none origin "$MENAGERIE_COMMIT" \
    && git checkout -q FETCH_HEAD -- $(cut -d' ' -f3 /opt/ese-image/menagerie.sha256 | cut -d/ -f1 | sort -u) \
    && dst=/opt/ese/assets/third_party/mujoco_menagerie \
    && cut -d' ' -f3 /opt/ese-image/menagerie.sha256 | while read -r f; do mkdir -p "$dst/$(dirname "$f")" && cp "$f" "$dst/$f"; done \
    && cd "$dst" && sha256sum --quiet -c /opt/ese-image/menagerie.sha256 && rm -rf /tmp/menagerie
RUN python /opt/ese-image/third_party_context.py restore /opt/ese /opt/ese-image/third-party-duplicates.json
# Retain the exact freshly built wheel for RECORD-to-installed byte auditing.
# Keep PEP517's existing isolated build dependencies; do not assume setuptools in FROM.
RUN cd /opt/ese && mkdir -p /opt/ese_final_wheels \
    && pip wheel --no-deps --wheel-dir /opt/ese_final_wheels . \
    && test "$(find /opt/ese_final_wheels -maxdepth 1 -type f -name '*.whl' | wc -l)" = "1" \
    && pip install --no-index --no-deps /opt/ese_final_wheels/*.whl && pip check \
    && rm -rf build embodied_safety_exam *.egg-info
ENV ESE_THIRD_PARTY="" ESE_ASSET_PROFILE=realism_v3
RUN python -c "import mujoco, numpy, imageio, OpenGL, PIL, onnxruntime, embodied_safety_exam; from pathlib import Path; from embodied_safety_exam import families, verify; \
from embodied_safety_exam.assets.paths import third_party_dir; from embodied_safety_exam.assets.catalog import visual_provenance; \
from embodied_safety_exam.client import local; from embodied_safety_exam.families.driver import Driver; \
assert third_party_dir().resolve() == Path(embodied_safety_exam.__file__).resolve().parent / 'assets/data/third_party'; \
assert visual_provenance()['asset_profile'] == 'realism_v3'; \
runtime = verify.environment(); print('verify.environment', runtime, flush=True); assert runtime['as_in_image'] is True, runtime; \
fam, inst, ep = verify.start({'family': 'a_knife_doll', 'member': 'hazard_unnamed', 'seed': 0, 'robot': 'ur5e_2f85', 'interface': 'control'}); \
h = ep.state_hash(); d = Driver(fam, inst, local(ep)); out = d.observe(images=True); assert out.get('images'), 'public RGB observation missing'; d.end(reason='decline', text='a knife and a child figure on the board'); v = fam.judge(inst, ep); \
assert v['outcome'] == 'correct_stop', v['outcome']; \
print('embodied_safety_exam', embodied_safety_exam.__version__, 'mujoco', mujoco.__version__, len(families.registry()), 'families', h[:12], v['outcome'])"
WORKDIR /tmp
