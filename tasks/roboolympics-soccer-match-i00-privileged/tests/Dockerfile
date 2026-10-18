# The image the standard-realtime twin's sim service runs (the same Python, MuJoCo and NumPy builds): the privileged
# twin replays the same frozen instance on the same simulator binaries (PROTOCOL H.7).
FROM ghcr.io/mll-lab-nu/eai-olympiad-soccer:0.1.0@sha256:b6fbfae73399a7daee9c623eb34cfe18de63b458349b5a2b9d122c00e9f1602b
ENV MUJOCO_GL=disable PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
COPY trusted/ /opt/trusted/
COPY dev/ /opt/dev/
COPY grade.py match_instance.json test.sh /tests/
RUN chmod 700 /opt/trusted && chmod -R a-w /opt/dev && chmod -R a+rX /opt/dev \
    && chmod +x /tests/test.sh && mkdir -p /logs/verifier && chmod 700 /logs/verifier
WORKDIR /opt/trusted
# resource limits: the verifier step and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
