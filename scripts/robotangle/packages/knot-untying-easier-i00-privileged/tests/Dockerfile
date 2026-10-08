# Separate verifier sandbox (PROTOCOL §4): the same simulator image with the verifier's own copies of the
# tooling and the frozen instance baked in. Nothing the agent did in its container reaches this one — Harbor
# uploads only the declared artifacts (/app/output/), so a patched success check or a swapped interpreter in
# the agent container cannot influence the verdict.
FROM obejw/rcb-topogym:0.2.16-dev-cu128
COPY runtime_binding.json /tests/runtime_binding.json
COPY grade.py instance.json rcb_topogym.py test.sh /tests/
COPY instance_assets/ /tests/instance_assets/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests:/opt/topogym
WORKDIR /tests
