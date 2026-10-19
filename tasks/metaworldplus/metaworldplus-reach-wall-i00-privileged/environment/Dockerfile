# MetaWorld+ privileged task: the Meta-World image, the task's tooling and its frozen instance.
FROM ghcr.io/mll-lab-nu/efe:metaworld-0.1.0
COPY instance.npz /app/instance.npz
COPY --from=ghcr.io/mll-lab-nu/efe:metaworldplus-files-0.1.0@sha256:71ed06f7370f8f3f855842b19c4f9062fc4454b1329530c0c2b44751ef4fa44d /privileged/environment/mw_tool.py /opt/tools/mw_tool.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
