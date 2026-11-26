FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.7.0@sha256:1397f5ba078dbbb9cff655c1ed962b72c3f42282d3bb5f2002f72209401249d2 /privileged/environment/hands.py /privileged/environment/checker.py /privileged/environment/essential.py /privileged/environment/essential_articulated.py /privileged/environment/essential_held_joystick_scene.py /privileged/environment/essential_inhand.py /privileged/environment/essential_pen_regrasp_scene.py /privileged/environment/essential_rotary_gait_scene.py /privileged/environment/essential_rotary_multi.py /privileged/environment/essential_two_object_scene.py /privileged/environment/essential_visual.py /privileged/environment/replay.py /privileged/environment/runtime.py /privileged/environment/scene.py /privileged/environment/variants/0ecb32e466/catalog.json /opt/tools/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
