# Separate verifier sandbox (PROTOCOL §4): the same simulator image with the verifier's own copies of the
# tooling and the frozen instance baked in. Nothing the agent did in its container reaches this one — Harbor
# uploads only the declared artifacts (/app/output/), so a patched success check or a swapped interpreter in
# the agent container cannot influence the verdict.
FROM ghcr.io/mll-lab-nu/eai-robotangle:0.2.22
COPY runtime_binding.json /tests/runtime_binding.json
COPY grade.py rcb_topogym.py test.sh /tests/
RUN python /opt/robotangle/stage_instance.py horseshoe-ring-medium-i00 /tests --purge   # the frozen instance, from the image (scripts/robotangle/assets.json), checked against runtime_binding.json
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests:/opt/topogym
WORKDIR /tests
