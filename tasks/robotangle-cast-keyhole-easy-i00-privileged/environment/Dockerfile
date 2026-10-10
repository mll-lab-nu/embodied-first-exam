# Base image = TopoGym's simulator (see images/topogym/). Everything task-specific is copied here.
FROM ghcr.io/mll-lab-nu/eai-robotangle:0.2.22
COPY runtime_binding.json /app/runtime_binding.json
RUN python /opt/robotangle/stage_instance.py cast-keyhole-easy-i00 /app --purge   # the frozen instance, from the image (scripts/robotangle/assets.json), checked against runtime_binding.json
COPY rcb_topogym.py /opt/tools/rcb_topogym.py
ENV PYTHONPATH=/opt/tools:/opt/topogym
# the longest trajectory the verifier replays within its timeout (scripts/robotangle/mk_tasks.py row_cap)
ENV RCB_MAX_STEPS=200000
RUN mkdir -p /app/output
WORKDIR /app
