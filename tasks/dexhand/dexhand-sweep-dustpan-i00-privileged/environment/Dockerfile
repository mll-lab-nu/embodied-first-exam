FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.5.0@sha256:e90c3817d6fee11cd727b5f82252740849e5b66ced87c7fce411b4747e911166 /privileged/environment/hands.py /privileged/environment/variants/99a6471895/catalog.json /privileged/environment/variants/8ae9cbedaa/checker.py /privileged/environment/variants/e8cd4d53ee/replay.py /privileged/environment/variants/2ef7f8ba38/runtime.py /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.5.0@sha256:e90c3817d6fee11cd727b5f82252740849e5b66ced87c7fce411b4747e911166 /privileged/environment/assets/external_assets.json /privileged/environment/assets/reset.npz /privileged/environment/assets/reset_wuji.npz /privileged/environment/assets/sweep_sharpa.xml /opt/tools/assets/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
