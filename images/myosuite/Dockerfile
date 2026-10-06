# eai-myosuite: MyoSuite 2.12.2 (Apache-2.0) on MuJoCo 3.6.0: musculoskeletal models of the human hand and arm (MyoHand:
# 39 muscles; MyoArm: 34 or 63 muscles), with the model files (simhive) that ship in the wheel. Infrastructure only:
# the upstream package, no benchmark code; tasks `FROM` it and COPY their own tooling. CPU only (MuJoCo physics,
# OSMesa rendering). Tag = images/myosuite/VERSION. Build from the repo root: scripts/build_images.sh (or
#   docker build -f images/myosuite/Dockerfile -t ghcr.io/mll-lab-nu/eai-myosuite:$(cat images/myosuite/VERSION) .)
# Same stack as the image the frozen instances were made with (rcb-myosuite:0.1.1); every pip package is pinned (the
# closure of the install line), so a rebuild reproduces the instances' state hashes (scripts/myosuite/README.md).
# 0.1.1: numpy 2.3.5 instead of 2.4.6. MyoSuite 2.12.2's Bimanual, Soccer and ChaseTag envs call float() on 1-element
# arrays, which numpy 2.4 rejects; every instance hash and every reference / positive-example replay of the first ten
# families is bit-identical under both versions.
FROM python@sha256:e41613d42d4891e4930f79523f93f81bbc7632584ec65e36ab055f41a800b41e
RUN apt-get update && apt-get install -y --no-install-recommends git libosmesa6 libgl1 libegl1 ffmpeg && \
    rm -rf /var/lib/apt/lists/*
# Install and scrub in ONE layer: MyoSuite ships trained NPG baseline policies (myosuite/agents/), the source of this
# benchmark's reference solutions. A later layer deleting them would leave them in this layer's blob for anyone who
# pulls the image; nothing in MyoSuite imports them.
RUN pip install --no-cache-dir \
      MyoSuite==2.12.2 mujoco==3.6.0 gymnasium==1.2.3 numpy==2.3.5 scipy==1.17.1 ImageIO==2.38.0 imageio-ffmpeg==0.6.0 \
      absl-py==2.5.0 click==8.5.0 cloudpickle==3.1.2 etils==1.14.0 Farama-Notifications==0.0.6 flatten-dict==0.5.0 \
      fsspec==2026.9.0 gitdb==4.0.12 GitPython==3.1.62 glfw==2.10.2 h5py==3.16.0 packaging==26.3 pillow==12.3.0 \
      pink-noise-rl==2.0.1 psutil==7.2.2 PyOpenGL==3.1.10 smmap==5.0.3 termcolor==3.3.0 typing_extensions==4.16.0 \
      zipp==4.1.0 && \
    rm -rf /usr/local/lib/python3.11/site-packages/myosuite/agents && \
    ! find /usr/local/lib/python3.11/site-packages/myosuite \( -name "*.pickle" -o -name "*.pkl" -o -name "*.zip" \) | grep .
ENV MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa PYTHONUNBUFFERED=1
RUN python -c "import myosuite; print(myosuite.__version__)"
WORKDIR /app
