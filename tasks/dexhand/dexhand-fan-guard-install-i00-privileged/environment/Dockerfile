FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.11.0@sha256:5bd382fdadf7a766bfdb014dd30350f5c1a5f87e5bcb559a3a0539b2d2cce7aa /privileged/environment/hands.py /privileged/environment/variants/5504b0fa5b/catalog.json /privileged/environment/variants/19a12120ad/checker.py /privileged/environment/geometry.py /privileged/environment/variants/fef84ad4b3/replay.py /privileged/environment/variants/7e3fcc99ed/runtime.py /privileged/environment/variants/594155d137/scene.py /privileged/environment/variants/e8011d953f/task.json /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.11.0@sha256:5bd382fdadf7a766bfdb014dd30350f5c1a5f87e5bcb559a3a0539b2d2cce7aa /privileged/environment/assets/blade-0.stl /privileged/environment/assets/blade-1.stl /privileged/environment/assets/blade-2.stl /opt/tools/assets/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
