# Separate verifier sandbox (PROTOCOL §4): the same simulator image with the verifier's own copies of the
# tooling and the frozen instance baked in. Nothing the agent did in its container reaches this one — Harbor
# uploads only the declared artifacts (/app/output/), so a patched success check or a swapped interpreter in
# the agent container cannot influence the verdict.
FROM ghcr.io/mll-lab-nu/eai-robotangle:0.2.22
COPY runtime_binding.json /tests/runtime_binding.json
COPY grade.py rcb_topogym.py test.sh /tests/
RUN python /opt/robotangle/stage_instance.py horseshoe-ring-easier-i00 /tests --purge   # the frozen instance, from the image (scripts/robotangle/assets.json), checked against runtime_binding.json
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests:/opt/topogym
# the longest trajectory the verifier replays within its timeout (scripts/robotangle/mk_tasks.py row_cap)
ENV RCB_MAX_STEPS=200000 RCB_VERIFIER_BUDGET_S=45000
WORKDIR /tests
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
