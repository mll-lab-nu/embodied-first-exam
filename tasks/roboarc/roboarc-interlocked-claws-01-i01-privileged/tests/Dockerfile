# Separate verifier sandbox (PROTOCOL §4): the same simulator image with the verifier's own copies of the
# tooling and the frozen instance baked in. Nothing the agent did in its container reaches this one — Harbor
# uploads only the declared artifacts (/app/output/), so a patched success check or a swapped interpreter in
# the agent container cannot influence the verdict.
FROM ghcr.io/mll-lab-nu/efe:roboarc-0.2.0
# MuJoCo task: numpy / OpenBLAS SIMD masking, so every CPU class generates the frozen bytes
ENV NPY_DISABLE_CPU_FEATURES=AVX512F,AVX512CD,AVX512_SKX,AVX512_CLX,AVX512_CNL,AVX512_ICL,AVX512_SPR OPENBLAS_CORETYPE=Haswell
COPY runtime_binding.json /tests/runtime_binding.json
COPY grade.py test.sh /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:roboarc-files-0.1.0@sha256:3ebbe4b6947849941de2dd5b9af0592ead637da1bd9125df1a1b0d584ea4a49a /rcb_topogym.py /tests/rcb_topogym.py
COPY --from=ghcr.io/mll-lab-nu/efe:roboarc-files-0.1.0@sha256:3ebbe4b6947849941de2dd5b9af0592ead637da1bd9125df1a1b0d584ea4a49a /render_bridge.py /tests/render_bridge.py
COPY --from=ghcr.io/mll-lab-nu/efe:roboarc-files-0.1.0@sha256:3ebbe4b6947849941de2dd5b9af0592ead637da1bd9125df1a1b0d584ea4a49a /nyx_direct.py /tests/nyx_direct.py
RUN python /opt/robotangle/stage_instance.py interlocked-claws-01-i01 /tests --purge   # the frozen instance, from the image (images/roboarc/assets.json), checked against runtime_binding.json
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests:/opt/topogym
# the longest trajectory the verifier replays within its timeout
ENV RCB_MAX_STEPS=200000 RCB_VERIFIER_BUDGET_S=45000
WORKDIR /tests
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.2.0@sha256:65442d9e9eeb493d785a59d48a321345e2b48186946cc9d55beb684182514b4b /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
