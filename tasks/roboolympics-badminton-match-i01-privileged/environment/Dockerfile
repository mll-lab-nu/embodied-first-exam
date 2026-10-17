# The image the standard-realtime twin's sim service runs (the same Python, MuJoCo and NumPy builds): the privileged
# twin replays the same frozen instance on the same simulator binaries (PROTOCOL H.7).
FROM ghcr.io/mll-lab-nu/eai-olympiad:0.1.0@sha256:99255569bf68bcf27f4e4867b58bad55c1d54fe73281920882e97c310836b6c7
ENV MUJOCO_GL=disable PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
COPY fullsim/ /opt/fullsim/
ENV PYTHONPATH=/opt/fullsim
WORKDIR /app
RUN mkdir -p /app/output && chmod -R a+rX /opt/fullsim
