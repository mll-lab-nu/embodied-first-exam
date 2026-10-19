# Separate verifier sandbox (PROTOCOL §4, Appendix H.1): eai-ispatialgym as built (its BDDL problems and upstream's own
# success check), the frozen start every copy shares, this task's goal.json (restored onto it and checked against
# upstream's TRO by sha256), the measured facts and the tooling. Only /app/output/ reaches it.
FROM ghcr.io/mll-lab-nu/efe-private:ispatialgym-0.2.0
COPY instance.json goal.json facts.json upstream.json test.sh /tests/
COPY --from=ghcr.io/mll-lab-nu/efe:ispatialgym-files-0.2.0@sha256:f07933a4ac0bab0b0743f4754d67587798e70e47c10057c44827a94d6cbb8ea9 /privileged/environment/rcb_ispatialgym.py /privileged/tests/grade.py /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV OMNIGIBSON_HEADLESS=1
WORKDIR /tests
# resource limits: the verifier step (from the monitor image) and its copy of the limits (docs/protocol/README.md §2.10) # rcb-monitor
COPY --from=ghcr.io/mll-lab-nu/efe:monitor-0.2.0@sha256:65442d9e9eeb493d785a59d48a321345e2b48186946cc9d55beb684182514b4b /opt/rcb_monitor/rcb_limits.py /tests/rcb_limits.py
COPY rcb_limits.json /tests/rcb_limits.json
