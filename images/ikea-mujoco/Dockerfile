# ikea-mujoco: MuJoCo 3.14.0 (CPU, float64; the wheel with the EPA horizon fix byte-patched in) and the IKEA furniture scenes.
# Build context: images/ikea-mujoco/stage_context.py writes images/ikea-mujoco/context/ (scenes/<task>/, checked
# against images/ikea-mujoco/assets.json). No task code here: the tooling and graders are copied by each task.
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
# mujoco's dependencies pinned to the versions of the published 0.3.0 image, so a local build installs the same set
RUN pip install --no-cache-dir mujoco==3.14.0 numpy==2.5.4 absl-py==2.5.1 etils==1.14.0 fsspec==2026.9.0 glfw==2.10.2 \
      PyOpenGL==3.1.10 typing_extensions==4.16.0 websockets==17.2 zipp==4.1.1
# MuJoCo 3.14.0 + the EPA horizon-overflow fix as a 14-byte patch of the wheel's own libmujoco.so (images/ikea-mujoco/mujoco-3.14.0-epa/:
# upstream 6d662aed; sha256 5e7623e3... -> 52e2a24e927ccac047b13576ff9fcbe455bc9a12b0d2e0bf1868bb7ca5be2e4d, asserted by
# the script; bit-identical to the stock wheel on every IKEA reference, no SIGSEGV on eket's crash reproducers)
COPY bytepatch_libmujoco.py /tmp/bytepatch_libmujoco.py
RUN python /tmp/bytepatch_libmujoco.py \
      "$(python -c 'import mujoco, os; print(os.path.dirname(mujoco.__file__))')/libmujoco.so.3.14.0" \
 && rm /tmp/bytepatch_libmujoco.py \
 && echo "52e2a24e927ccac047b13576ff9fcbe455bc9a12b0d2e0bf1868bb7ca5be2e4d  $(python -c 'import mujoco, os; print(os.path.dirname(mujoco.__file__))')/libmujoco.so.3.14.0" | sha256sum -c -
COPY scenes/ /opt/ikea/scenes/
COPY assets.json /opt/ikea/assets.json
RUN chmod -R a+rX,go-w /opt/ikea
# numpy / OpenBLAS SIMD masking (as the RoboARC image): the scenes' mechanisms compute with numpy, whose AVX-512 and
# AVX2 reductions differ in the last bit; unmasked, eket's reference diverged on Zen 4 hosts before row 20000 and
# crashed MuJoCo (SIGSEGV at row 29396), while Intel AVX2 hosts replayed it. Masked, both classes give the same hashes.
ENV IKEA_SCENES=/opt/ikea/scenes OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
    NPY_DISABLE_CPU_FEATURES=AVX512F,AVX512CD,AVX512_SKX,AVX512_CLX,AVX512_CNL,AVX512_ICL,AVX512_SPR \
    OPENBLAS_CORETYPE=Haswell
WORKDIR /app
