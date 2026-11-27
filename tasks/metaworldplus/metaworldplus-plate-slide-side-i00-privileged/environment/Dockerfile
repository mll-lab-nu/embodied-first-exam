# MetaWorld+ privileged task: the Meta-World image, the task's tooling and its frozen instance.
FROM ghcr.io/mll-lab-nu/efe:metaworld-0.1.0
COPY instance.npz /app/instance.npz
COPY --from=ghcr.io/mll-lab-nu/efe:metaworldplus-files-0.8.0@sha256:7548af1c69100c873291a277e9c0963c1e4a44f41b41f75c8d530dbba11f4f9f /privileged/environment/mw_tool.py /opt/tools/mw_tool.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
