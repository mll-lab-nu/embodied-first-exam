# VLABench privileged task: the VLABench image, the task's tooling and its frozen instance.
FROM ghcr.io/mll-lab-nu/efe-private:vlabench-0.1.0
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe-private:vlabench-files-0.1.0@sha256:40a954b7f643e4bb280cdf5e07c3f086a1bda555785977e704b085b30211da17 /privileged/environment/vlb_tool.py /opt/tools/vlb_tool.py
ENV PYTHONPATH=/opt/tools:/opt/VLABench:/opt/rrt-algorithms
RUN mkdir -p /app/output
WORKDIR /app
