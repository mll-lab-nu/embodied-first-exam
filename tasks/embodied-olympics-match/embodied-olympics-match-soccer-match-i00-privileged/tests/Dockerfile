# The image the standard-realtime twin's sim service runs (the same Python, MuJoCo and NumPy builds): the privileged
# twin replays the same frozen instance on the same simulator binaries (PROTOCOL H.7).
FROM ghcr.io/mll-lab-nu/efe:olympiad-soccer-0.1.0@sha256:b6fbfae73399a7daee9c623eb34cfe18de63b458349b5a2b9d122c00e9f1602b
ENV MUJOCO_GL=disable PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
COPY trusted/ /opt/trusted/
COPY dev/ /opt/dev/
COPY match_instance.json test.sh /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.1.1@sha256:90ff02735ace55c77f571a3c7fd602ef0fb295fd27837d6734e5b7cc3cf5cc05 /privileged/tests/grade.py /tests/grade.py
RUN chmod 700 /opt/trusted && chmod -R a-w /opt/dev && chmod -R a+rX /opt/dev \
    && chmod +x /tests/test.sh && mkdir -p /logs/verifier && chmod 700 /logs/verifier
WORKDIR /opt/trusted
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.2.0@sha256:65442d9e9eeb493d785a59d48a321345e2b48186946cc9d55beb684182514b4b /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
