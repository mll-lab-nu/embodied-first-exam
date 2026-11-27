# MetaWorld+ privileged task: the Meta-World image, the task's tooling and its frozen instance.
FROM ghcr.io/mll-lab-nu/efe:metaworld-0.1.0
COPY instance.npz /app/instance.npz
COPY --from=ghcr.io/mll-lab-nu/efe:metaworldplus-files-0.6.0@sha256:3dd85a27b4f1605b031ab3e5e0798e12944f8b00e5c550a6b73769e22a4177de /privileged/environment/mw_tool.py /opt/tools/mw_tool.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
