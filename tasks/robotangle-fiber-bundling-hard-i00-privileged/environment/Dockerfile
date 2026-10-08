# Base image = TopoGym's simulator (see images/topogym/). Everything task-specific is copied here.
FROM ghcr.io/mll-lab-nu/eai-robotangle:0.2.21
COPY runtime_binding.json /app/runtime_binding.json
RUN python /opt/robotangle/stage_instance.py fiber-bundling-hard-i00 /app --purge   # the frozen instance, from the image (scripts/robotangle/assets.json), checked against runtime_binding.json
COPY rcb_topogym.py /opt/tools/rcb_topogym.py
ENV PYTHONPATH=/opt/tools:/opt/topogym
RUN mkdir -p /app/output
WORKDIR /app
