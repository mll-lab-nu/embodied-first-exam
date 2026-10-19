FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /opt/tools/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.1.0@sha256:47919ae95e25b8c6daa3c19c9714a4743fd1c18db580589cb8552a71aa689f9d /privileged/environment/hands.py /privileged/environment/checker.py /privileged/environment/essential.py /privileged/environment/essential_articulated.py /privileged/environment/essential_held_joystick_scene.py /privileged/environment/essential_inhand.py /privileged/environment/essential_pen_regrasp_scene.py /privileged/environment/essential_rotary_gait_scene.py /privileged/environment/essential_rotary_multi.py /privileged/environment/essential_two_object_scene.py /privileged/environment/essential_visual.py /privileged/environment/replay.py /privileged/environment/runtime.py /privileged/environment/scene.py /privileged/environment/variants/a7abab4f26/catalog.json /opt/tools/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
