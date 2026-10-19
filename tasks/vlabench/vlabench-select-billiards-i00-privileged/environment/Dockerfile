# VLABench privileged task: the VLABench image, the task's tooling and its frozen instance.
FROM ghcr.io/mll-lab-nu/efe-private:vlabench-0.1.0
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe:vlabench-files-0.2.0@sha256:f5d2fd8b386a90292984125c4c5fa4da919e12ebbe6218a745a36c7eef740a42 /privileged/environment/vlb_tool.py /opt/tools/vlb_tool.py
ENV PYTHONPATH=/opt/tools:/opt/VLABench:/opt/rrt-algorithms
RUN mkdir -p /app/output
WORKDIR /app
