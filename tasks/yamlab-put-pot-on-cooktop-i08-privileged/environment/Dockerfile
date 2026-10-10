# Base image = YAMLab + Isaac Lab / Isaac Sim 5.1 + the two tasks' object assets (see images/yamlab/; BUILD_ONLY).
# Everything task-specific is copied here; YAMLab's demonstrations are not in the image.
FROM ghcr.io/mll-lab-nu/eai-yamlab:0.1.0
COPY instance.json /app/instance.json
COPY rcb_yamlab.py /opt/tools/rcb_yamlab.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
