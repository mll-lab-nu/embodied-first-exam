# Base image = TopoGym's simulator (see images/topogym/). Everything task-specific is copied here.
FROM ghcr.io/mll-lab-nu/eai-robotangle:0.2.18
COPY instance.json /app/instance.json
COPY runtime_binding.json /app/runtime_binding.json
COPY instance_assets/ /app/instance_assets/
COPY rcb_topogym.py /opt/tools/rcb_topogym.py
ENV PYTHONPATH=/opt/tools:/opt/topogym
RUN mkdir -p /app/output
WORKDIR /app
