# Base image = TopoGym's simulator (see images/topogym/). Everything task-specific is copied here.
FROM topogym-local/buzz-wire-variants:20261002-01
COPY instance.json /app/instance.json
COPY instance_assets/ /app/instance_assets/
COPY rcb_topogym.py /opt/tools/rcb_topogym.py
ENV PYTHONPATH=/opt/tools:/opt/topogym
RUN mkdir -p /app/output
WORKDIR /app
