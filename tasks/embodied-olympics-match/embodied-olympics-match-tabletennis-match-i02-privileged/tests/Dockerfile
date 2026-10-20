# The image the standard-realtime twin's sim service runs (same Python, MuJoCo 3.3.7, NumPy 2.2.6 build): the
# privileged twin replays the same frozen instance on the same simulator binaries (PROTOCOL H.7).
FROM ghcr.io/mll-lab-nu/efe:olympiad-0.1.0@sha256:99255569bf68bcf27f4e4867b58bad55c1d54fe73281920882e97c310836b6c7
ENV MUJOCO_GL=disable PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
COPY trusted/ /opt/trusted/
COPY dev/ /opt/dev/
COPY match_instance.json test.sh /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.1.2@sha256:c0925be70f6af507ffa373b136519456d18c283af22e5ea6a74700bab88cd9bb /privileged/tests/variants/6477110667/grade.py /tests/grade.py
RUN chmod 700 /opt/trusted && chmod -R a-w /opt/dev && chmod -R a+rX /opt/dev \
    && chmod +x /tests/test.sh && mkdir -p /logs/verifier && chmod 700 /logs/verifier
WORKDIR /opt/trusted
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.3.0@sha256:53154417782408df8309194971b08b18c3682d2b337e2e3b2eb4c88fe025ab85 /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
