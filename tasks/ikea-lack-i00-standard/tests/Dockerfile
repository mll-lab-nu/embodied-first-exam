# Separate verifier sandbox: the IKEA MuJoCo image (MuJoCo 3.14.0 + the frozen scenes) with the verifier's own copies of
# the scene runtime and the binding. It grades the sim service's artifacts (/data) and replays /data/trajectory.npz itself.
FROM ghcr.io/mll-lab-nu/eai-ikea-mujoco:0.3.0
COPY grade.py replay_grade.py rcb_ikea.py test.sh runtime_binding.json /tests/
RUN chmod +x /tests/test.sh && mkdir -p /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
