# >>> images/tactilelab/Dockerfile
# tactilelab: Isaac Sim 5.1.0 + Isaac Lab 2.3.2 (Python 3.11, torch 2.7.0 cu128) + Pink IK for the TactileLab tasks (dual-arm
# X-Trainer, two GelSight Mini sensors on the right gripper). Infrastructure only, no task code: the tasks take the
# tactilelab_tasks package and their tooling from the files-only image tactilelab-files. Isaac Sim needs an RTX-class GPU even
# headless; a task's compose reserves it and mounts a trial-scoped cache volume at /cache (shader/extension cache).
# The recipe needs no build context. Building it accepts the NVIDIA Isaac Sim / Omniverse licence (images/tactilelab/BUILD_ONLY).
FROM docker.io/nvidia/cuda:12.8.1-base-ubuntu22.04@sha256:001469ea0f3dec85a1ca929aeea3b58ae369d4c11228b10aec1f642bb6ca7a6f AS tactilelab-base
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 UV_LINK_MODE=copy \
    NVIDIA_DRIVER_CAPABILITIES=all VK_DRIVER_FILES=/etc/vulkan/icd.d/nvidia_icd.json \
    OMNI_KIT_ACCEPT_EULA=YES ACCEPT_EULA=Y OMNI_KIT_ALLOW_ROOT=1
# system libraries from the Ubuntu archive as it was on 2026-10-01 (snapshot.ubuntu.com), and the NVIDIA Vulkan / EGL loader entries
RUN rm -f /etc/apt/sources.list.d/cuda*.list && \
    sed -i -e 's|http://archive.ubuntu.com/ubuntu/|http://snapshot.ubuntu.com/ubuntu/20261001T000000Z/|' \
           -e 's|http://security.ubuntu.com/ubuntu/|http://snapshot.ubuntu.com/ubuntu/20261001T000000Z/|' /etc/apt/sources.list && \
    apt-get -o Acquire::Retries=10 update && apt-get -o Acquire::Retries=10 install -y --no-install-recommends \
      curl ca-certificates git git-lfs ffmpeg \
      libvulkan1 libegl1 libgl1 libglvnd0 libglu1-mesa libx11-6 libxt6 libxext6 libxrender1 libxi6 libxrandr2 libxinerama1 \
      libxcursor1 libsm6 libice6 libgomp1 libglib2.0-0 libxkbcommon0 libxkbcommon-x11-0 libfontconfig1 libfreetype6 && \
    rm -rf /var/lib/apt/lists/* && mkdir -p /etc/vulkan/icd.d /etc/vulkan/implicit_layer.d /usr/share/glvnd/egl_vendor.d && \
    printf '{\n    "file_format_version" : "1.0.0",\n    "ICD" : {\n        "library_path" : "libGLX_nvidia.so.0",\n        "api_version" : "1.3.194"\n    }\n}\n' > /etc/vulkan/icd.d/nvidia_icd.json && \
    printf '{\n    "file_format_version" : "1.0.0",\n    "layer": {\n        "name": "VK_LAYER_NV_optimus",\n        "type": "INSTANCE",\n        "library_path": "libGLX_nvidia.so.0",\n        "api_version" : "1.3.194",\n        "implementation_version" : "1",\n        "description" : "NVIDIA Optimus layer",\n        "functions": {\n            "vkGetInstanceProcAddr": "vk_optimusGetInstanceProcAddr",\n            "vkGetDeviceProcAddr": "vk_optimusGetDeviceProcAddr"\n        },\n        "enable_environment": {\n            "__NV_PRIME_RENDER_OFFLOAD": "1"\n        },\n        "disable_environment": {\n            "DISABLE_LAYER_NV_OPTIMUS_1": ""\n        }\n    }\n}\n' > /etc/vulkan/implicit_layer.d/nvidia_layers.json && \
    printf '{\n    "file_format_version" : "1.0.0",\n    "ICD" : {\n        "library_path" : "libEGL_nvidia.so.0"\n    }\n}\n' > /usr/share/glvnd/egl_vendor.d/10_nvidia.json
COPY --from=ghcr.io/astral-sh/uv:0.13.0@sha256:cdc6093146eb3ff6a40107b38f008b789e050e77ad87865e381d9917da55a168 /uv /uvx /root/.local/bin/
ENV PATH="/root/.local/bin:${PATH}"
# the Isaac 5.1 stack in /opt/tactilelab/.venv: torch 2.7.0 (CUDA 12.8 wheels), isaacsim from pypi.nvidia.com, Isaac Lab 2.3.2
# (flatdict, one of its dependencies, builds with pkg_resources: setuptools < 81 and no build isolation), Pink IK
RUN uv python install 3.11.17 && uv venv -p 3.11.17 /opt/tactilelab/.venv && \
    VIRTUAL_ENV=/opt/tactilelab/.venv uv pip install "torch==2.7.0" "torchvision==0.22.0" --index-url https://download.pytorch.org/whl/cu128 && \
    VIRTUAL_ENV=/opt/tactilelab/.venv uv pip install "isaacsim[all,extscache]==5.1.0" --extra-index-url https://pypi.nvidia.com && \
    VIRTUAL_ENV=/opt/tactilelab/.venv uv pip install "setuptools<81" wheel && \
    VIRTUAL_ENV=/opt/tactilelab/.venv uv pip install --no-build-isolation "flatdict==4.0.1" && \
    VIRTUAL_ENV=/opt/tactilelab/.venv uv pip install "isaaclab[isaacsim,all]==2.3.2" --extra-index-url https://pypi.nvidia.com && \
    VIRTUAL_ENV=/opt/tactilelab/.venv uv pip install "pin-pink==4.2.0" "daqp" "h5py" "pyyaml" "scipy" "imageio[ffmpeg]" && \
    rm -rf /root/.cache/uv
# Pink IK's own stack at the versions the tasks were developed with (pinocchio 2.x, which the line above resolves to,
# does not load with pin-pink 4.2); numpy goes back to Isaac Sim 5.1's 1.26 without touching the rest
# (its replicator graph breaks on numpy 2; pin 4.0 declares numpy >= 2 but runs on 1.26, as in the tasks' development setup)
RUN VIRTUAL_ENV=/opt/tactilelab/.venv uv pip install "pin==4.0.0" "pin-pink==4.2.0" "daqp==0.7.2" "qpsolvers==4.8.2" && \
    VIRTUAL_ENV=/opt/tactilelab/.venv uv pip install --no-deps --reinstall "numpy==1.26.0" && \
    rm -rf /root/.cache/uv
# Pin: the steps above follow the install sequence the tasks were developed with; this one sets every package of the Isaac
# environment to the version of the reference build (the list below, 229 packages, without resolving), removes any package an
# unpinned step above pulls in today that the list does not hold, and fails unless the environment is exactly the list
RUN printf '%s\n' \
      'absl-py==2.5.1' \
      'aioboto3==15.1.0' \
      'aiobotocore==2.24.0' \
      'aiodns==3.1.1' \
      'aiofiles==23.2.1' \
      'aiohappyeyeballs==2.4.4' \
      'aiohttp==3.11.11' \
      'aioitertools==0.11.0' \
      'aiosignal==1.3.2' \
      'annotated-doc==0.0.5' \
      'annotated-types==0.8.0' \
      'antlr4-python3-runtime==4.9.3' \
      'anyio==4.14.2' \
      'asteval==1.0.6' \
      'async-timeout==5.0.1' \
      'attrs==25.1.0' \
      'awscrt==0.23.8' \
      'azure-core==1.28.0' \
      'azure-identity==1.13.0' \
      'azure-storage-blob==12.17.0' \
      'boto3==1.39.11' \
      'botocore==1.39.11' \
      'certifi==2026.10.23' \
      'cffi==2.1.1' \
      'charset-normalizer==3.3.2' \
      'click==8.1.7' \
      'cloudpickle==3.1.2' \
      'cmeel==0.61.0' \
      'cmeel-assimp==6.0.5' \
      'cmeel-boost==1.90.0' \
      'cmeel-console-bridge==1.0.2.3' \
      'cmeel-octomap==1.10.0' \
      'cmeel-qhull==8.0.2.1' \
      'cmeel-tinyxml==2.6.2.3' \
      'cmeel-tinyxml2==11.0.0' \
      'cmeel-urdfdom==6.0.0' \
      'cmeel-zlib==1.3.2' \
      'coal==3.0.3' \
      'contourpy==1.3.1' \
      'coverage==7.4.4' \
      'cryptography==44.0.0' \
      'cycler==0.11.0' \
      'daqp==0.7.2' \
      'decorator==5.3.1' \
      'eigenpy==3.13.0' \
      'einops==0.8.2' \
      'farama-notifications==0.0.6' \
      'fastapi==0.115.7' \
      'filelock==3.13.1' \
      'flaky==3.8.1' \
      'flatdict==4.0.1' \
      'fonttools==4.55.3' \
      'frozenlist==1.5.0' \
      'fsspec==2024.6.1' \
      'gitdb==4.0.12' \
      'gitpython==3.2.1' \
      'grpcio==1.85.0' \
      'gunicorn==23.0.0' \
      'gymnasium==1.2.0' \
      'h11==0.16.0' \
      'h5py==3.16.0' \
      'hf-xet==1.7.0' \
      'hidapi==0.14.0.post2' \
      'hpp-fcl==2.4.4' \
      'httpcore==1.0.9' \
      'httptools==0.6.1' \
      'httpx==0.28.1' \
      'huggingface-hub==1.16.1' \
      'hydra-core==1.3.8' \
      'idna==3.10' \
      'idna-ssl==1.1.0' \
      'imageio==2.37.0' \
      'imageio-ffmpeg==0.7.0' \
      'importlib-metadata==10.1.0' \
      'iniconfig==2.3.1' \
      'isaaclab==2.3.2' \
      'isaacsim==5.1.0.0' \
      'isaacsim-app==5.1.0.0' \
      'isaacsim-asset==5.1.0.0' \
      'isaacsim-benchmark==5.1.0.0' \
      'isaacsim-code-editor==5.1.0.0' \
      'isaacsim-core==5.1.0.0' \
      'isaacsim-cortex==5.1.0.0' \
      'isaacsim-example==5.1.0.0' \
      'isaacsim-extscache-kit==5.1.0.0' \
      'isaacsim-extscache-kit-sdk==5.1.0.0' \
      'isaacsim-extscache-physics==5.1.0.0' \
      'isaacsim-gui==5.1.0.0' \
      'isaacsim-kernel==5.1.0.0' \
      'isaacsim-replicator==5.1.0.0' \
      'isaacsim-rl==5.1.0.0' \
      'isaacsim-robot==5.1.0.0' \
      'isaacsim-robot-motion==5.1.0.0' \
      'isaacsim-robot-setup==5.1.0.0' \
      'isaacsim-ros1==5.1.0.0' \
      'isaacsim-ros2==5.1.0.0' \
      'isaacsim-sensor==5.1.0.0' \
      'isaacsim-storage==5.1.0.0' \
      'isaacsim-template==5.1.0.0' \
      'isaacsim-test==5.1.0.0' \
      'isaacsim-utils==5.1.0.0' \
      'isodate==0.6.1' \
      'jinja2==3.1.6' \
      'jmespath==1.0.1' \
      'junitparser==5.0.3' \
      'kiwisolver==1.4.4' \
      'lazy-loader==0.4' \
      'libcoal==3.0.3' \
      'libpinocchio==4.0.0' \
      'llvmlite==0.42.0' \
      'loop-rate-limiters==1.2.0' \
      'markdown==3.11.2' \
      'markdown-it-py==4.2.0' \
      'markupsafe==2.1.3' \
      'matplotlib==3.10.3' \
      'mdurl==0.1.2' \
      'ml-dtypes==0.5.4' \
      'moviepy==2.2.1' \
      'mpmath==1.3.0' \
      'msal==1.27.0' \
      'msal-extensions==1.0.0' \
      'multidict==6.1.0' \
      'nest-asyncio==1.5.6' \
      'networkx==3.3' \
      'numba==0.59.1' \
      'numpy==1.26.0' \
      'nvidia-cublas-cu12==12.8.3.14' \
      'nvidia-cuda-cupti-cu12==12.8.57' \
      'nvidia-cuda-nvrtc-cu12==12.8.61' \
      'nvidia-cuda-runtime-cu12==12.8.57' \
      'nvidia-cudnn-cu12==9.7.1.26' \
      'nvidia-cufft-cu12==11.3.3.41' \
      'nvidia-cufile-cu12==1.13.0.11' \
      'nvidia-curand-cu12==10.3.9.55' \
      'nvidia-cusolver-cu12==11.7.2.55' \
      'nvidia-cusparse-cu12==12.5.7.53' \
      'nvidia-cusparselt-cu12==0.6.3' \
      'nvidia-nccl-cu12==2.26.2' \
      'nvidia-nvjitlink-cu12==12.8.61' \
      'nvidia-nvtx-cu12==12.8.55' \
      'oauthlib==3.2.2' \
      'omegaconf==2.3.1' \
      'onnx==1.23.2' \
      'onnx-ir==1.1.0' \
      'onnxscript==0.7.2' \
      'opencv-python-headless==4.11.0.86' \
      'orjson==3.13.0' \
      'osqp==0.6.7.post3' \
      'packaging==23.0' \
      'pandas==3.0.6' \
      'pillow==11.3.0' \
      'pin==4.0.0' \
      'pin-pink==4.2.0' \
      'pint==0.20.1' \
      'pluggy==1.7.0' \
      'portalocker==2.7.0' \
      'prettytable==3.3.0' \
      'proglog==0.1.12' \
      'propcache==0.2.1' \
      'protobuf==7.36.2' \
      'psutil==5.9.8' \
      'pycares==4.8.0' \
      'pycparser==3.12' \
      'pydantic==2.11.10' \
      'pydantic-core==2.33.2' \
      'pyglet==1.5.31' \
      'pygments==2.21.0' \
      'pyjwt==2.15.1' \
      'pyparsing==3.0.9' \
      'pyperclip==1.8.0' \
      'pypng==0.20220715.0' \
      'pytest==9.1.1' \
      'pytest-mock==3.17.0' \
      'python-dateutil==2.9.0.post0' \
      'python-dotenv==1.2.4' \
      'python-multipart==0.0.20' \
      'pytz==2024.1' \
      'pyvers==0.2.3' \
      'pyyaml==6.0.2' \
      'qdldl==0.1.7.post5' \
      'qpsolvers==4.8.2' \
      'qrcode==7.4.2' \
      'regex==2026.9.29' \
      'requests==2.32.3' \
      'requests-oauthlib==1.3.1' \
      'rich==15.0.0' \
      'rsl-rl-lib==3.0.1' \
      'rtree==1.3.0' \
      's3transfer==0.13.1' \
      'safetensors==0.8.0' \
      'scikit-image==0.24.0' \
      'scipy==1.15.3' \
      'sentry-sdk==2.29.1' \
      'setuptools==78.1.0' \
      'shellingham==1.5.4' \
      'six==1.17.0' \
      'skrl==2.1.1' \
      'smmap==5.0.3' \
      'stable-baselines3==2.8.0' \
      'starlette==0.45.3' \
      'sympy==1.13.3' \
      'tensorboard==2.21.0' \
      'tensorboard-data-server==0.7.2' \
      'tensordict==0.14.3' \
      'tifffile==2024.8.30' \
      'tokenizers==0.23.3' \
      'toml==0.10.2' \
      'torch==2.7.0+cu128' \
      'torchaudio==2.7.0' \
      'torchvision==0.22.0+cu128' \
      'tornado==6.5.1' \
      'tqdm==4.70.1' \
      'transformers==5.17.0' \
      'trimesh==4.5.1' \
      'triton==3.3.0' \
      'typer==0.27.3' \
      'typing-extensions==4.12.2' \
      'typing-inspection==0.4.2' \
      'urllib3==2.8.0' \
      'uvicorn==0.29.0' \
      'warp-lang==1.18.0' \
      'watchdog==4.0.0' \
      'wcwidth==0.9.4' \
      'websockets==12.0' \
      'werkzeug==3.1.9' \
      'wheel==0.48.0' \
      'wrapt==1.16.0' \
      'yarl==1.18.3' \
      'zipp==4.1.2' \
      > /opt/tactilelab/requirements.lock && \
    VIRTUAL_ENV=/opt/tactilelab/.venv uv pip install --no-deps --index-strategy unsafe-best-match \
      --extra-index-url https://download.pytorch.org/whl/cu128 --extra-index-url https://pypi.nvidia.com \
      -r /opt/tactilelab/requirements.lock && rm -rf /root/.cache/uv && \
    VIRTUAL_ENV=/opt/tactilelab/.venv uv pip freeze | grep -vxFf /opt/tactilelab/requirements.lock | sed 's/[ =@].*//' | \
      xargs -r env VIRTUAL_ENV=/opt/tactilelab/.venv uv pip uninstall && \
    VIRTUAL_ENV=/opt/tactilelab/.venv uv pip freeze | diff - /opt/tactilelab/requirements.lock && echo "environment == requirements.lock"
ENV PATH="/opt/tactilelab/.venv/bin:${PATH}" VIRTUAL_ENV=/opt/tactilelab/.venv
# the Newton sidecar of the cloth / cable / dough / FEM tasks: its own Python 3.12 environment (Newton needs warp >= 1.17,
# the Isaac side ships 1.12); the tasks' sidecar code goes next to it, in /opt/tactilelab/sidecar (from tactilelab-files)
RUN uv python install 3.12.13 && uv venv -p 3.12.13 /opt/tactilelab/sidecar/.venv && \
    VIRTUAL_ENV=/opt/tactilelab/sidecar/.venv uv pip install --no-deps "newton==1.7.0" "warp-lang==1.18.0" "numpy==2.5.4" && \
    rm -rf /root/.cache/uv
ENV WARP_CACHE_PATH=/cache/warp
# Kit caches (shaders, extension registry, user data) live under /cache so a task's compose can keep them in a volume
RUN mkdir -p /cache/ov-cache /cache/ov-data /cache/ov-logs /root/.cache /root/.local/share /root/.nvidia-omniverse /app/output && \
    ln -s /cache/ov-cache /root/.cache/ov && ln -s /cache/ov-data /root/.local/share/ov && ln -s /cache/ov-logs /root/.nvidia-omniverse/logs
# apt read the Ubuntu archive snapshot above, so the build's packages stay pinned; the image itself points apt back at the
# Ubuntu archive (the base image's sources.list, byte for byte): an `apt-get update` at run time is fast and reliable
RUN sed -i -e '/ jammy-security /s|http://snapshot.ubuntu.com/ubuntu/20261001T000000Z/|http://security.ubuntu.com/ubuntu/|' \
           -e 's|http://snapshot.ubuntu.com/ubuntu/20261001T000000Z/|http://archive.ubuntu.com/ubuntu/|' /etc/apt/sources.list && \
    echo "15a39563d491def84446c8a5304e873a6b6509d56e2b54edce8eea154e1290a0  /etc/apt/sources.list" | sha256sum -c -
WORKDIR /app
# <<< images/tactilelab/Dockerfile

# Base image = Isaac Lab 2.3.2 / Isaac Sim 5.1 + Pink IK (see images/tactilelab/). Everything task-specific is copied here:
# the tactilelab_tasks package as the agent may read it (no scripted policies, no expert parameters) and the tooling.
FROM tactilelab-base
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:tactilelab-files-0.7.0@sha256:a36dfcd052277a5805394f2dc729aeba68d0d3d2e6c61293b057b32a5725d4b3 /tactilelab_tasks /opt/tactilelab/tactilelab_tasks
COPY --from=ghcr.io/mll-lab-nu/efe:tactilelab-assets-files-0.1.0@sha256:d58c3a36a5f5ea031d65f14b95c3c4f7c68268f5d9977dd1b963ce286bd6bcd7 /tactilelab_tasks /opt/tactilelab/tactilelab_tasks
COPY --from=ghcr.io/mll-lab-nu/efe:tactilelab-thirdparty-files-0.1.0@sha256:2071f1a6d29b4cdd65fac011fb98ff5ff21dac15a00121d984a851acc5aa7a15 /tactilelab_tasks /opt/tactilelab/tactilelab_tasks
COPY --from=ghcr.io/mll-lab-nu/efe:tactilelab-files-0.7.0@sha256:a36dfcd052277a5805394f2dc729aeba68d0d3d2e6c61293b057b32a5725d4b3 /sidecar /opt/tactilelab/sidecar
COPY --from=ghcr.io/mll-lab-nu/efe:tactilelab-files-0.7.0@sha256:a36dfcd052277a5805394f2dc729aeba68d0d3d2e6c61293b057b32a5725d4b3 /rcb_tactilelab.py /opt/tools/rcb_tactilelab.py
ENV PYTHONPATH=/opt/tools:/opt/tactilelab
RUN mkdir -p /app/output
WORKDIR /app
