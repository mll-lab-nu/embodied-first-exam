# eai-ambench: AM-Bench (github.com/ambench/ambench @ 60bf5b7, Apache-2.0; aerial manipulation on Isaac Lab) on Isaac Sim 5.1.0 +
# Isaac Lab @ f4aa17f, torch 2.7.0+cu128, with AM-Bench's own controller dependencies at the commits its superproject pins
# (Pyroki @ 2eafc99 with JAX 0.4.28 on the CPU, acados @ fa0af20 built with qpOASES). What is left out on purpose: AM-Bench's
# scripted experts (source/ambench/ambench/policies/scripted/, the reference solutions; the task registrations' pointer to them is
# blanked), its policy-learning package (ambench_learn), its scripts, documentation and git history: nothing an agent can read
# here locates a solution (docs/protocol/README.md §2.7). Every web asset the twelve tasks' scenes load at run time (objects'
# payloads and materials, the robot's paint, Isaac Lab's ground, NDT's warehouse scene) is baked in under /opt/isaac-assets
# (images/ambench/web_assets.txt), mirroring the asset buckets' layouts: the tasks run with closed egress.
# Tag = images/ambench/VERSION; build from the repo root (images/ambench/BUILD_ONLY has the command, licences and checks):
#   docker build -f images/ambench/Dockerfile -t ghcr.io/mll-lab-nu/eai-ambench:$(cat images/ambench/VERSION) .
# Every Python package is pinned in images/ambench/requirements.lock (`uv pip freeze` of the reference build).
# BUILD_ONLY, never published: Isaac Sim 5.1 / Omniverse Kit may be installed and used but not redistributed.
# The layers up to Isaac Lab are YAMLab's (images/yamlab/Dockerfile), the same Isaac Sim / Isaac Lab stack.
FROM nvidia/cuda:12.8.1-base-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 UV_LINK_MODE=copy \
    NVIDIA_DRIVER_CAPABILITIES=all VK_DRIVER_FILES=/etc/vulkan/icd.d/nvidia_icd.json \
    OMNI_KIT_ACCEPT_EULA=YES ACCEPT_EULA=Y OMNI_KIT_ALLOW_ROOT=1 PRIVACY_CONSENT=N
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates git git-lfs ffmpeg cmake build-essential \
      libvulkan1 libegl1 libgl1 libglvnd0 libglu1-mesa libx11-6 libxt6 libxext6 libxrender1 libxi6 libxrandr2 libxinerama1 \
      libxcursor1 libsm6 libice6 libgomp1 libglib2.0-0 libxkbcommon0 libxkbcommon-x11-0 libfontconfig1 libfreetype6 && \
    rm -rf /var/lib/apt/lists/* && mkdir -p /etc/vulkan/icd.d /etc/vulkan/implicit_layer.d /usr/share/glvnd/egl_vendor.d && \
    printf '{\n    "file_format_version" : "1.0.0",\n    "ICD" : {\n        "library_path" : "libGLX_nvidia.so.0",\n        "api_version" : "1.3.194"\n    }\n}\n' > /etc/vulkan/icd.d/nvidia_icd.json && \
    printf '{\n    "file_format_version" : "1.0.0",\n    "layer": {\n        "name": "VK_LAYER_NV_optimus",\n        "type": "INSTANCE",\n        "library_path": "libGLX_nvidia.so.0",\n        "api_version" : "1.3.194",\n        "implementation_version" : "1",\n        "description" : "NVIDIA Optimus layer",\n        "functions": {\n            "vkGetInstanceProcAddr": "vk_optimusGetInstanceProcAddr",\n            "vkGetDeviceProcAddr": "vk_optimusGetDeviceProcAddr"\n        },\n        "enable_environment": {\n            "__NV_PRIME_RENDER_OFFLOAD": "1"\n        },\n        "disable_environment": {\n            "DISABLE_LAYER_NV_OPTIMUS_1": ""\n        }\n    }\n}\n' > /etc/vulkan/implicit_layer.d/nvidia_layers.json && \
    printf '{\n    "file_format_version" : "1.0.0",\n    "ICD" : {\n        "library_path" : "libEGL_nvidia.so.0"\n    }\n}\n' > /usr/share/glvnd/egl_vendor.d/10_nvidia.json
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/opt/venv/bin:/root/.local/bin:${PATH}" VIRTUAL_ENV=/opt/venv
RUN uv python install 3.11 && uv venv --seed -p 3.11 /opt/venv
# the GPU stack first (largest layers): torch 2.7.0+cu128, then Isaac Sim 5.1.0 from pypi.nvidia.com
RUN uv pip install torch==2.7.0 torchvision==0.22.0 --index-url https://download.pytorch.org/whl/cu128 && rm -rf /root/.cache/uv
RUN uv pip install "isaacsim[all,extscache]==5.1.0" --extra-index-url https://pypi.nvidia.com && rm -rf /root/.cache/uv
# Isaac Lab at YAMLab's pinned commit, its extensions only ("none": no RL frameworks)
RUN git clone -q https://github.com/isaac-sim/IsaacLab.git /opt/IsaacLab && cd /opt/IsaacLab && \
    git checkout -q f4aa17f87e2e5db5484f0b5974918573e8918ce2 && echo Yes | TERM=xterm ./isaaclab.sh --install none && rm -rf /root/.cache/pip /root/.cache/uv
# AM-Bench, scrubbed, with its Pyroki and acados submodules (the commits AM-Bench pins), installed as its scripts/setup/install.sh does
ARG AMBENCH_COMMIT=60bf5b73041df4eab571f7d9f0a297aeecbf2e0d
RUN git clone -q https://github.com/ambench/ambench.git /tmp/ambench && cd /tmp/ambench && git checkout -q "$AMBENCH_COMMIT" && \
    git submodule update -q --init --recursive ext/pyroki ext/acados && mkdir -p /opt/ambench/ext && \
    cp LICENSE THIRD_PARTY_NOTICES.md /opt/ambench/ && cp -r source /opt/ambench/source && \
    cp -r ext/pyroki ext/acados /opt/ambench/ext/ && cd / && rm -rf /tmp/ambench && \
    find /opt/ambench -name .git -prune -exec rm -rf {} + && \
    rm -rf /opt/ambench/source/ambench_learn /opt/ambench/source/ambench/ambench/policies/scripted && \
    find /opt/ambench/source -name "*.md" -delete && \
    sed -i -E 's/scripted_policy_entry_point="[^"]*"/scripted_policy_entry_point=""/' /opt/ambench/source/ambench/ambench/tasks/*/__init__.py && \
    if grep -rIn -e "policies.scripted" -e "policies/scripted" -e "ambench_learn" /opt/ambench/source; then echo "scrub incomplete"; exit 1; fi
RUN cd /opt/ambench && pip install --no-cache-dir -e ext/pyroki && pip install --no-cache-dir "numpy==1.26.0" "jax==0.4.28" "jaxlib==0.4.28" && \
    cmake -S ext/acados -B ext/acados/build -DACADOS_WITH_QPOASES=ON > /dev/null && \
    cmake --build ext/acados/build --target install --parallel 8 > /dev/null && \
    pip install --no-cache-dir -e ext/acados/interfaces/acados_template && pip install --no-cache-dir -e source/ambench
ENV JAX_PLATFORMS=cpu ACADOS_SOURCE_DIR=/opt/ambench/ext/acados \
    LD_LIBRARY_PATH=/opt/ambench/ext/acados/lib:/opt/ambench/ext/acados/build
# Web assets (2269 files, ~0.95 GB, each checked against its sha256), mirroring the buckets' layouts: the tooling sets
# Isaac's asset root to /opt/isaac-assets/Assets/Isaac/5.1 (the ground, the wall's material, NDT's warehouse scene), and
# localize_assets.py rewrites the URLs thirteen of AM-Bench's USDs load from the buckets (objects' payloads and materials, the
# robot's paint) to the copies. The USD rewrite uses a throwaway usd-core: Isaac Sim's own pxr loads only inside Kit.
COPY images/ambench/web_assets.txt images/ambench/localize_assets.py /opt/isaac-assets/
RUN set -e; grep -v '^#' /opt/isaac-assets/web_assets.txt | xargs -P 16 -L 1 sh -c \
      'mkdir -p "$(dirname "$2")" && curl -sSfL --retry 5 -o "$2" "$1" && echo "$0  $2" | sha256sum -c --quiet -' && \
    A=/opt/ambench/source/ambench/ambench/assets; \
    python -m venv /tmp/usdv && /tmp/usdv/bin/pip install -q --no-cache-dir usd-core==25.5 && \
    /tmp/usdv/bin/python /opt/isaac-assets/localize_assets.py \
      https://omniverse-content-production.s3-us-west-2.amazonaws.com/=/opt/isaac-assets/ \
      https://omniverse-content-production.s3.us-west-2.amazonaws.com/=/opt/isaac-assets/ \
      http://omniverse-content-production.s3-us-west-2.amazonaws.com/=/opt/isaac-assets/ \
      https://omniverse-content-staging.s3.us-west-2.amazonaws.com/=/opt/isaac-assets/staging/ \
      https://omniverse-content-staging.s3-us-west-2.amazonaws.com/=/opt/isaac-assets/staging/ -- \
      $A/objects/cline.usd $A/objects/container.usd $A/objects/door.usd $A/objects/frame.usd $A/objects/hole.usd \
      $A/objects/lemon.usd $A/objects/lever.usd $A/objects/lime.usd $A/objects/marked_region.usda $A/objects/peg.usd \
      $A/objects/push_button.usd $A/robots/configuration/end_effector_base.usd $A/robots/configuration/hexa_scorpion_base.usd && \
    rm -rf /tmp/usdv
# Pin: the steps above follow AM-Bench's scripts/setup/install.sh; this one sets every package to the version of the reference
# build (images/ambench/requirements.lock, without resolving), and the build fails unless the result is exactly the lock
# (editable checkouts aside: Isaac Lab, Pyroki, acados_template and AM-Bench at the commits above).
COPY images/ambench/requirements.lock /opt/requirements.lock
RUN uv pip install --no-deps --index-strategy unsafe-best-match --extra-index-url https://download.pytorch.org/whl/cu128 \
      --extra-index-url https://pypi.nvidia.com -r /opt/requirements.lock && rm -rf /root/.cache/uv && \
    uv pip freeze --exclude-editable | diff - /opt/requirements.lock && echo "environment == requirements.lock"
# Kit caches (shaders, extension registry, user data) live under /cache so a task's compose can keep them in a volume
RUN mkdir -p /cache/ov-cache /cache/ov-data /cache/ov-logs /root/.cache /root/.local/share /root/.nvidia-omniverse /app/output && \
    ln -s /cache/ov-cache /root/.cache/ov && ln -s /cache/ov-data /root/.local/share/ov && ln -s /cache/ov-logs /root/.nvidia-omniverse/logs
WORKDIR /app
