FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.6.0@sha256:76ecdba39db6329198383e5fa6c89613bd95185ab974a2895521d32237900b24 /privileged/environment/hands.py /privileged/environment/variants/2f2a9b1205/catalog.json /privileged/environment/checker.py /privileged/environment/essential.py /privileged/environment/essential_articulated.py /privileged/environment/essential_held_joystick_scene.py /privileged/environment/essential_inhand.py /privileged/environment/essential_pen_regrasp_scene.py /privileged/environment/essential_rotary_gait_scene.py /privileged/environment/essential_rotary_multi.py /privileged/environment/essential_two_object_scene.py /privileged/environment/essential_visual.py /privileged/environment/replay.py /privileged/environment/runtime.py /privileged/environment/scene.py /opt/tools/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
