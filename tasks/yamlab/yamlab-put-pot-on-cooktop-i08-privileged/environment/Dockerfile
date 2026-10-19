# Base image = YAMLab + Isaac Lab / Isaac Sim 5.1 + the two tasks' object assets (see images/yamlab/; BUILD_ONLY).
# Everything task-specific is copied here; YAMLab's demonstrations are not in the image.
FROM ghcr.io/mll-lab-nu/efe-private:yamlab-0.1.0
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:yamlab-files-0.2.0@sha256:dcf2cdbd2b6dc96201e6c66f15fdb65a44098e8e27abc7a316375ceb1168cf85 /privileged/environment/rcb_yamlab.py /opt/tools/rcb_yamlab.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
