# Separate verifier sandbox (PROTOCOL §4): the same simulator image with the verifier's own copies of the
# tooling, the robot config and the frozen instance baked in (the grader, the tooling and the robot config from the
# files-only image eai-behavior-files, pinned by digest). Nothing the agent did in its container reaches this
# one — Harbor uploads only the declared artifacts (/app/output/), so a patched success check or a swapped
# interpreter in the agent container cannot influence the verdict.
FROM ghcr.io/mll-lab-nu/efe-private:behavior-0.1.1
COPY instance.json test.sh /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:behavior-files-0.2.0@sha256:e2594de8dd89711e917968ab5dc01d13f614f6e9844f05263ae67736109f3f85 /privileged/grade.py /tests/grade.py
COPY --from=ghcr.io/mll-lab-nu/efe:behavior-files-0.2.0@sha256:e2594de8dd89711e917968ab5dc01d13f614f6e9844f05263ae67736109f3f85 /rcb_behavior.py /tests/rcb_behavior.py
COPY --from=ghcr.io/mll-lab-nu/efe:behavior-files-0.2.0@sha256:e2594de8dd89711e917968ab5dc01d13f614f6e9844f05263ae67736109f3f85 /r1pro_primitives_eval.yaml /tests/r1pro_primitives_eval.yaml
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
# this task's state-dump patch (sitecustomize.py, imported at startup from PYTHONPATH): the state can be dumped on the
# step a log is split (board 0178); the shared tooling is unchanged
COPY sitecustomize.py /tests/sitecustomize.py
ENV PYTHONHASHSEED=0
WORKDIR /tests
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.2.0@sha256:65442d9e9eeb493d785a59d48a321345e2b48186946cc9d55beb684182514b4b /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
