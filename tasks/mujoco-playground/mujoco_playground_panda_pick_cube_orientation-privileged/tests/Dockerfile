# Separate verifier sandbox (PROTOCOL §4): the MuJoCo image with the verifier's own copies of the tooling and the
# frozen instance; only the declared artifacts (/app/output/) arrive from the agent.
FROM ghcr.io/mll-lab-nu/efe:mujoco-0.1.2
COPY instance.json test.sh /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:mujoco-playground-files-0.1.1@sha256:fbd7136fbe91fbbb5458c7c4354ec2abb744ce55e230e8251cba8a9e85399435 /privileged/environment/rcb_panda.py /privileged/tests/variants/c5bde2d42e/grade.py /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.2.0@sha256:65442d9e9eeb493d785a59d48a321345e2b48186946cc9d55beb684182514b4b /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
