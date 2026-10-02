# MetaWorld+ privileged task: the Meta-World image, the task's tooling and its frozen instance.
FROM ghcr.io/mll-lab-nu/eai-metaworld:0.1.0
COPY instance.npz /app/instance.npz
COPY mw_tool.py /opt/tools/mw_tool.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
