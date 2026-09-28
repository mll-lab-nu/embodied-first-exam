FROM ghcr.io/jameskrw/rcb-mujoco:0.1.0
COPY instance.json /app/instance.json
COPY rcb_dtb.py /opt/tools/rcb_dtb.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
