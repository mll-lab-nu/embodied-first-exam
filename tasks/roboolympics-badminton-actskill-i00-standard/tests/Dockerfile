# Separate verifier sandbox (tools/export_fexam.py, kind engineer): the sport's image, our simulator directory
# (root only: the skill runs as nobody), the toolkit at the seat's paths, the development request set.
FROM ghcr.io/mll-lab-nu/eai-olympiad:0.1.0
RUN pip install --no-cache-dir scipy==1.18.1
COPY sim /srv/sim
COPY toolkit/opt/robot/act_cases_public.jsonl /opt/robot/act_cases_public.jsonl
COPY toolkit/opt/robot/assets /opt/robot/assets
COPY toolkit/opt/robot/lib/bm_kinematics.py /opt/robot/lib/bm_kinematics.py
COPY toolkit/opt/robot/lib/bm_servo.py /opt/robot/lib/bm_servo.py
COPY toolkit/opt/robot/robot_only.xml /opt/robot/robot_only.xml
COPY toolkit/opt/robot/toolkit.toml /opt/robot/toolkit.toml
COPY test.sh engineer_grade.py /tests/
RUN chmod 700 /srv/sim && chmod +x /tests/test.sh
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
