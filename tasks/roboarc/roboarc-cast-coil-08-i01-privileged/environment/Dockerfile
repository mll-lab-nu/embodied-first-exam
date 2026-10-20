# Base image = TopoGym's simulator (see images/topogym/). Everything task-specific is copied here.
FROM ghcr.io/mll-lab-nu/efe:roboarc-0.2.0
# MuJoCo task: numpy / OpenBLAS SIMD masking, so every CPU class generates the frozen bytes
ENV NPY_DISABLE_CPU_FEATURES=AVX512F,AVX512CD,AVX512_SKX,AVX512_CLX,AVX512_CNL,AVX512_ICL,AVX512_SPR OPENBLAS_CORETYPE=Haswell
COPY runtime_binding.json /app/runtime_binding.json
RUN python /opt/robotangle/stage_instance.py cast-coil-08-i01 /app --purge   # the frozen instance, from the image (images/roboarc/assets.json), checked against runtime_binding.json
COPY --from=ghcr.io/mll-lab-nu/efe:roboarc-files-0.1.0@sha256:3ebbe4b6947849941de2dd5b9af0592ead637da1bd9125df1a1b0d584ea4a49a /rcb_topogym.py /opt/tools/rcb_topogym.py
COPY --from=ghcr.io/mll-lab-nu/efe:roboarc-files-0.1.0@sha256:3ebbe4b6947849941de2dd5b9af0592ead637da1bd9125df1a1b0d584ea4a49a /render_bridge.py /opt/tools/render_bridge.py
COPY --from=ghcr.io/mll-lab-nu/efe:roboarc-files-0.1.0@sha256:3ebbe4b6947849941de2dd5b9af0592ead637da1bd9125df1a1b0d584ea4a49a /nyx_direct.py /opt/tools/nyx_direct.py
ENV PYTHONPATH=/opt/tools:/opt/topogym
# the longest trajectory the verifier replays within its timeout
ENV RCB_MAX_STEPS=200000
RUN mkdir -p /app/output
WORKDIR /app
