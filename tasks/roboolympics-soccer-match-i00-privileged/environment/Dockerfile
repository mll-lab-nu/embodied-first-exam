# The image the standard-realtime twin's sim service runs (the same Python, MuJoCo and NumPy builds): the privileged
# twin replays the same frozen instance on the same simulator binaries (PROTOCOL H.7).
FROM ghcr.io/mll-lab-nu/eai-olympiad-soccer:0.1.0@sha256:b6fbfae73399a7daee9c623eb34cfe18de63b458349b5a2b9d122c00e9f1602b
ENV MUJOCO_GL=disable PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
COPY fullsim/ /opt/fullsim/
ENV PYTHONPATH=/opt/fullsim
WORKDIR /app
RUN mkdir -p /app/output && chmod -R a+rX /opt/fullsim
