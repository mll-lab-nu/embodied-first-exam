FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.11.0@sha256:4e16e8b63a4d2c93ed37a7a8b24ba27238c4a81764b9a9f02446640defa55519 /privileged/environment/hands.py /privileged/environment/variants/99a6471895/catalog.json /privileged/environment/variants/8ae9cbedaa/checker.py /privileged/environment/variants/10264b47a7/replay.py /privileged/environment/variants/0ffe598f38/runtime.py /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.11.0@sha256:4e16e8b63a4d2c93ed37a7a8b24ba27238c4a81764b9a9f02446640defa55519 /privileged/environment/assets/external_assets.json /privileged/environment/assets/reset.npz /privileged/environment/assets/reset_wuji.npz /privileged/environment/assets/sweep_sharpa.xml /opt/tools/assets/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
