# Base image = YAMLab + Isaac Lab / Isaac Sim 5.1 + the two tasks' object assets (see images/yamlab/; BUILD_ONLY).
# Everything task-specific is copied here; YAMLab's demonstrations are not in the image.
FROM ghcr.io/mll-lab-nu/efe-private:yamlab-0.1.0
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe-private:yamlab-files-0.1.0@sha256:ef6bd2b1ac385d0fb702e3129722330655bd0836a2f93e142b61924e00ad384b /privileged/environment/rcb_yamlab.py /opt/tools/rcb_yamlab.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
