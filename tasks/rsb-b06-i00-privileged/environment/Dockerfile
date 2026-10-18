# Privileged mode: RoboSafeBench's simulator (eai-robosafe, images/robosafe/) in the agent's own container. Its scripted
# solutions (every family's reference, literal execution and named strategies) are removed before the agent starts
# (scrub.py; docs/benchmarks/robosafe.md "Privileged tasks"). Everything task-specific is copied here.
FROM ghcr.io/mll-lab-nu/eai-robosafe:0.5.4
COPY scrub.py /tmp/scrub.py
RUN python /tmp/scrub.py && rm /tmp/scrub.py
COPY instance.json /app/instance.json
COPY rcb_rsb.py candidate_identity.py rcb_rsb_privileged.py /opt/tools/
ENV PYTHONPATH=/opt/tools RCB_RSB_INSTANCE=/app/instance.json
RUN mkdir -p /app/output
WORKDIR /app
