# Base image = TopoGym's simulator (see images/topogym/). Everything task-specific is copied here.
FROM ghcr.io/luigivamper/rcb-topogym:0.1.0
COPY instance.json /app/instance.json
COPY rcb_topogym.py /opt/tools/rcb_topogym.py
ENV PYTHONPATH=/opt/tools:/opt/topogym
RUN mkdir -p /app/output
WORKDIR /app
