FROM ghcr.io/mll-lab-nu/eai-sim_to_real:0.1.0
COPY instance.json /app/instance.json
COPY rcb_yam.py /opt/tools/rcb_yam.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
