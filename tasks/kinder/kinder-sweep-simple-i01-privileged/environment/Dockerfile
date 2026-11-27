# Base image = KinDER (images/kinder/). Everything task-specific is copied here.
FROM ghcr.io/mll-lab-nu/efe:kinder-0.1.6
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:kinder-files-0.6.0@sha256:e1dfaf4f772801e6f4b71d1d1e0de28f4f73ac53cff79b34bd43d9ee667bd2f3 /privileged/environment/rcb_kinder.py /opt/tools/rcb_kinder.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
