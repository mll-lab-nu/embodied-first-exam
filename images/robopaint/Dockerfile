# eai-robopaint (formerly rcb-robopaint, rcb-maniskill-paint): ManiSkill 3.0.1 (SAPIEN 3.0.3) + the Spline-FRIDA brush-stroke model
# (github.com/cmubig/Frida @ 1652973, GPL-3.0, weights included in that repository) + libmypaint 1.6.1 (ISC) with the
# mypaint-brushes 2.0.2 presets (CC0) for the brush families. Infrastructure only — contains no benchmark code: tasks `FROM` it and
# COPY their own tooling (rcb_brush.py). Tag = ghcr.io/mll-lab-nu/eai-robopaint:<images/robopaint/VERSION>
# (this image's own version); the build context is the repo root:
#   docker build -f images/robopaint/Dockerfile -t ghcr.io/mll-lab-nu/eai-robopaint:$(cat images/robopaint/VERSION) .
# Physics (PhysX) and the stroke models run on the CPU (torch CPU build). SAPIEN still needs a Vulkan device (the NVIDIA GPU) to
# build a scene at all (visual shapes create render materials) and to render the cameras: NVIDIA_DRIVER_CAPABILITIES=all makes the
# container runtime mount the driver's Vulkan/EGL libraries and the ICD json files below point the loaders at them. Tasks pass the
# GPU through with environment/docker-compose.yaml (and the verifier with tests/docker-compose.yaml).
# ---- libmypaint 1.6.1 (ISC) + the rcb_mypaint shim, built in a separate stage (the runtime stage below only copies /opt/mypaint)
FROM nvidia/cuda:12.4.1-base-ubuntu22.04 AS mypaint
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl gcc libc6-dev make pkg-config libjson-c-dev xz-utils && \
    rm -rf /var/lib/apt/lists/*
ARG LIBMYPAINT_URL=https://github.com/mypaint/libmypaint/releases/download/v1.6.1/libmypaint-1.6.1.tar.xz
ARG LIBMYPAINT_SHA256=741754f293f6b7668f941506da07cd7725629a793108bb31633fb6c3eae5315f
ARG BRUSHES_URL=https://github.com/mypaint/mypaint-brushes/releases/download/v2.0.2/mypaint-brushes-2.0.2.tar.xz
ARG BRUSHES_SHA256=7984a74edef94571d872d0629b224abaa956a36f632f5c5516b33d22e49eb566
# Determinism patch: libmypaint 1.6.1 mallocs the brush and its first stroke_to reads settings_value[] before computing it (valgrind),
# so results depended on heap contents; calloc zero-initialises it (and the smudge-bucket array). The build fails if it does not apply.
RUN cd /tmp && curl -LsSf -o lm.tar.xz "$LIBMYPAINT_URL" && echo "$LIBMYPAINT_SHA256  lm.tar.xz" | sha256sum -c - && tar xf lm.tar.xz && \
    cd libmypaint-1.6.1 && \
    sed -i 's|MyPaintBrush \*self = (MyPaintBrush \*)malloc(sizeof(MyPaintBrush));|MyPaintBrush *self = (MyPaintBrush *)calloc(1, sizeof(MyPaintBrush));|; s|float \*bucket_array = malloc(num_smudge_buckets \* SMUDGE_BUCKET_SIZE \* sizeof(float));|float *bucket_array = calloc((size_t)num_smudge_buckets * SMUDGE_BUCKET_SIZE, sizeof(float));|' mypaint-brush.c && \
    grep -q "calloc(1, sizeof(MyPaintBrush))" mypaint-brush.c && grep -q "bucket_array = calloc" mypaint-brush.c && \
    ./configure --prefix=/opt/mypaint --disable-introspection --without-glib --disable-i18n --disable-docs > /dev/null && \
    make -j4 > /dev/null && make install > /dev/null && cp COPYING /opt/mypaint/COPYING.libmypaint && cd /tmp && rm -rf lm.tar.xz libmypaint-1.6.1
COPY images/robopaint/rcb_mypaint.c /tmp/rcb_mypaint.c
RUN gcc -O2 -Wall -shared -fPIC -o /opt/mypaint/lib/librcbmypaint.so /tmp/rcb_mypaint.c -I/opt/mypaint/include/libmypaint -L/opt/mypaint/lib \
      -lmypaint -Wl,-rpath,/opt/mypaint/lib && cp /tmp/rcb_mypaint.c /opt/mypaint/
RUN cd /tmp && curl -LsSf -o br.tar.xz "$BRUSHES_URL" && echo "$BRUSHES_SHA256  br.tar.xz" | sha256sum -c - && tar xf br.tar.xz && \
    mkdir -p /opt/mypaint/brushes && cp -r mypaint-brushes-2.0.2/brushes/* /opt/mypaint/brushes/ && \
    cp mypaint-brushes-2.0.2/COPYING mypaint-brushes-2.0.2/AUTHORS /opt/mypaint/brushes/ && rm -rf br.tar.xz mypaint-brushes-2.0.2

# ---- the runtime image (0.1.1's layers unchanged, then libmypaint added at the end)
FROM nvidia/cuda:12.4.1-base-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 UV_LINK_MODE=copy NVIDIA_VISIBLE_DEVICES=all NVIDIA_DRIVER_CAPABILITIES=all
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git libvulkan1 libglvnd0 libgl1 libegl1 \
      libx11-6 libxext6 libxrender1 libgomp1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /usr/share/vulkan/icd.d /usr/share/glvnd/egl_vendor.d && \
    printf '{"file_format_version":"1.0.0","ICD":{"library_path":"libGLX_nvidia.so.0","api_version":"1.3.0"}}\n' > /usr/share/vulkan/icd.d/nvidia_icd.json && \
    printf '{"file_format_version":"1.0.0","ICD":{"library_path":"libEGL_nvidia.so.0"}}\n' > /usr/share/glvnd/egl_vendor.d/10_nvidia.json
RUN curl -LsSf https://astral.sh/uv/0.12.19/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
RUN uv python install 3.11 && uv venv -p 3.11 /opt/venv
ENV PATH="/opt/venv/bin:${PATH}" VIRTUAL_ENV=/opt/venv
# Python stack: images/robopaint/requirements.lock (uv pip compile of requirements.in: ManiSkill 3.0.1 + SAPIEN 3.0.3, and the
# stroke model's dependencies at the versions of FRIDA's own uv.lock; torch is the CPU build).
COPY images/robopaint/requirements.lock /tmp/requirements.lock
RUN uv pip install --no-deps -r /tmp/requirements.lock --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match && \
    rm -rf /root/.cache/uv /tmp/requirements.lock
# FRIDA at the pinned Spline-FRIDA commit (branch spline-frida-z-master-resolved). Kept: its LICENSE/README, the Python sources of
# src/ and src/mocap/ (param2stroke.py imports brush_stroke.py, which imports mocap/autoencoders.py) and each brush's learned
# stroke model (caches/<brush>/param2img.pt + calibration json). Dropped: the stroke-library photos, datasets, notebooks.
ARG FRIDA_COMMIT=1652973971bcd80f742a9d494f4e995fec34fd09
RUN git init -q /tmp/frida && cd /tmp/frida && git remote add origin https://github.com/cmubig/Frida.git && \
    git fetch -q --depth 1 origin "$FRIDA_COMMIT" && git checkout -q FETCH_HEAD && \
    mkdir -p /opt/frida/src/mocap /opt/frida/src/caches && cp LICENSE README.md /opt/frida/ && cp src/*.py /opt/frida/src/ && \
    cp src/mocap/*.py /opt/frida/src/mocap/ && \
    for d in src/caches/*/; do n=$(basename "$d"); if [ -f "$d/param2img.pt" ]; then mkdir -p "/opt/frida/src/caches/$n" && \
      cp "$d"/param2img.pt "$d"/*.json "/opt/frida/src/caches/$n/" 2>/dev/null; \
      cp "$d"/stroke_library/stroke_settings_during_library.json "/opt/frida/src/caches/$n/" 2>/dev/null; true; fi; done && \
    echo "$FRIDA_COMMIT" > /opt/frida/COMMIT && cd / && rm -rf /tmp/frida
ENV RCB_FRIDA_SRC=/opt/frida/src RCB_FRIDA_COMMIT=${FRIDA_COMMIT} MPLBACKEND=Agg
# Smoke test (no GPU at build time): ManiSkill + SAPIEN import; FRIDA's stroke model imports unmodified and loads its weights.
RUN cd /tmp && python -c "import mani_skill.envs, sapien, torch, sys; sys.path.insert(0, '/opt/frida/src'); import param2stroke as P; \
m = P.StrokeParametersToImage(); m.load_state_dict(torch.load('/opt/frida/src/caches/small_brush/param2img.pt', map_location='cpu', weights_only=True)); \
print('rcb-robopaint ok: mani_skill', mani_skill.__version__, 'sapien', sapien.__version__, 'torch', torch.__version__)"
WORKDIR /app
# libmypaint for the brushwork oil / acrylic tasks (since 0.2.0): the library, the shim, the presets (CC0) and json-c's runtime
RUN apt-get update && apt-get install -y --no-install-recommends libjson-c5 && rm -rf /var/lib/apt/lists/*
COPY --from=mypaint /opt/mypaint /opt/mypaint
ENV RCB_MYPAINT_LIB=/opt/mypaint/lib/librcbmypaint.so RCB_MYPAINT_BRUSHES=/opt/mypaint/brushes
RUN python -c "import ctypes, json; L = ctypes.CDLL('/opt/mypaint/lib/librcbmypaint.so'); L.rcb_brush_new.restype = ctypes.c_void_p; \
b = L.rcb_brush_new(open('/opt/mypaint/brushes/tanda/oil-01-paint.myb').read().encode()); assert b, 'preset did not load'; print('libmypaint ok')"
