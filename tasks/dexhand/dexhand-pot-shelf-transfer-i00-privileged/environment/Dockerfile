FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.8.0@sha256:d1dc5f258bcd214889ef9262f8b12da2ee997b55705f77e8b717629e6634ac6f /privileged/environment/hands.py /privileged/environment/variants/c655c8f528/catalog.json /privileged/environment/variants/224ae0a903/replay.py /privileged/environment/variants/c8196a34ef/runtime.py /privileged/environment/variants/daacb059fc/task.json /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.8.0@sha256:d1dc5f258bcd214889ef9262f8b12da2ee997b55705f77e8b717629e6634ac6f /privileged/environment/assets/variants/c3c6de27f8/manifest.json /privileged/environment/assets/pot_sharpa.xml /privileged/environment/assets/reset.json /opt/tools/assets/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.8.0@sha256:d1dc5f258bcd214889ef9262f8b12da2ee997b55705f77e8b717629e6634ac6f /privileged/environment/assets/pot/pot_0.stl /privileged/environment/assets/pot/pot_1.stl /privileged/environment/assets/pot/pot_4.stl /privileged/environment/assets/pot/pot_5.stl /privileged/environment/assets/pot/pot_6.stl /opt/tools/assets/pot/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
