# MetaWorld+ privileged task: the Meta-World image, the task's tooling and its frozen instance.
FROM ghcr.io/mll-lab-nu/efe:metaworld-0.1.0
COPY instance.npz /app/instance.npz
COPY --from=ghcr.io/mll-lab-nu/efe:metaworldplus-files-0.6.0@sha256:09ac45aaec635d01af066796ac853efe363c142fef70ab6fad3728edfedae05f /privileged/environment/mw_tool.py /opt/tools/mw_tool.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
