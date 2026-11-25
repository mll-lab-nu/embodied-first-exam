FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.6.1@sha256:31eb441eccc44a6da7e30ae46aae8eae10eead0d4dae1b50d15457541c911a1b /privileged/environment/hands.py /privileged/environment/variants/99a6471895/catalog.json /privileged/environment/variants/8ae9cbedaa/checker.py /privileged/environment/variants/10264b47a7/replay.py /privileged/environment/variants/0ffe598f38/runtime.py /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.6.1@sha256:31eb441eccc44a6da7e30ae46aae8eae10eead0d4dae1b50d15457541c911a1b /privileged/environment/assets/external_assets.json /privileged/environment/assets/reset.npz /privileged/environment/assets/reset_wuji.npz /privileged/environment/assets/sweep_sharpa.xml /opt/tools/assets/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
