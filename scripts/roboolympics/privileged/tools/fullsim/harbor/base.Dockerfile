# The image the standard-realtime twin's sim service runs (the same Python, MuJoCo and NumPy builds): the privileged
# twin replays the same frozen instance on the same simulator binaries (PROTOCOL H.7).
FROM @IMAGE@
ENV MUJOCO_GL=disable PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
