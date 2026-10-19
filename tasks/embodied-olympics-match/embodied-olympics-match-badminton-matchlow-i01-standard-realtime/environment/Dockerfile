# The player's container: no simulator, only Python with the standard client pins and the generic `game`
# command of the core (core/game.py, the sport's shortcuts filled in by tools/generate.py).
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
COPY client-requirements.txt /opt/client-requirements.txt
RUN pip install --no-cache-dir -r /opt/client-requirements.txt
COPY game /usr/local/bin/game
RUN chmod +x /usr/local/bin/game && mkdir -p /app/output
# sport.toml [seat] / [seat.low]: the player image's extras for this task
COPY seat_files/opt/robot/act_cases_public.jsonl /opt/robot/act_cases_public.jsonl
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.1.1@sha256:90ff02735ace55c77f571a3c7fd602ef0fb295fd27837d6734e5b7cc3cf5cc05 /shared/environment/fullsim/sports/badminton/presentation/assets/LICENSE.franka_emika_panda /opt/robot/assets/LICENSE.menagerie-franka
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.1.1@sha256:90ff02735ace55c77f571a3c7fd602ef0fb295fd27837d6734e5b7cc3cf5cc05 /shared/environment/fullsim/sports/badminton/sim/scene/assets/link0.stl /shared/environment/fullsim/sports/badminton/sim/scene/assets/link1.stl /shared/environment/fullsim/sports/badminton/sim/scene/assets/link2.stl /shared/environment/fullsim/sports/badminton/sim/scene/assets/link3.stl /shared/environment/fullsim/sports/badminton/sim/scene/assets/link4.stl /shared/environment/fullsim/sports/badminton/sim/scene/assets/link5_collision_0.obj /shared/environment/fullsim/sports/badminton/sim/scene/assets/link5_collision_1.obj /shared/environment/fullsim/sports/badminton/sim/scene/assets/link5_collision_2.obj /shared/environment/fullsim/sports/badminton/sim/scene/assets/link6.stl /shared/environment/fullsim/sports/badminton/sim/scene/assets/link7.stl /opt/robot/assets/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.1.1@sha256:90ff02735ace55c77f571a3c7fd602ef0fb295fd27837d6734e5b7cc3cf5cc05 /shared/environment/fullsim/sports/badminton/seat/lib/bm_kinematics.py /opt/robot/lib/bm_kinematics.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.1.1@sha256:90ff02735ace55c77f571a3c7fd602ef0fb295fd27837d6734e5b7cc3cf5cc05 /shared/environment/fullsim/sports/badminton/seat/lib/bm_servo.py /opt/robot/lib/bm_servo.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.1.1@sha256:90ff02735ace55c77f571a3c7fd602ef0fb295fd27837d6734e5b7cc3cf5cc05 /shared/environment/fullsim/sports/badminton/seat/robot_only.xml /opt/robot/robot_only.xml
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.1.1@sha256:90ff02735ace55c77f571a3c7fd602ef0fb295fd27837d6734e5b7cc3cf5cc05 /shared/environment/fullsim/sports/badminton/seat/toolkit.toml /opt/robot/toolkit.toml
RUN pip install --no-cache-dir -c /opt/client-requirements.txt mujoco==3.3.7 absl-py==2.5.0 etils==1.14.0 fsspec==2026.9.0 glfw==2.10.2 PyOpenGL==3.1.10 typing_extensions==4.16.0 zipp==4.1.0 && pip check
RUN python -c "import mujoco; m = mujoco.MjModel.from_xml_path('/opt/robot/robot_only.xml'); assert (m.njnt, m.nu) == (9, 9)"
RUN python -c "import sys; sys.path.insert(0, '/opt/robot/lib'); import bm_kinematics as k, bm_servo; K = k.RacketKinematics(); q, e = K.solve([0.3, -1.0, 1.2], normal=[0, 1, 0], base=[0.0, -1.6]); assert e < 1e-3, e; bm_servo.RobotSim()"
ENV SEAT=A
ENV SIM_URL=http://localhost:8000
# core 0.2.34: your skill server (game skill serve) and its port on the loopback the sim shares
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.1.1@sha256:90ff02735ace55c77f571a3c7fd602ef0fb295fd27837d6734e5b7cc3cf5cc05 /shared/environment/fullsim/skilleval/host.py /standard-realtime/environment/skillkit/sandbox.py /standard-realtime/environment/skillkit/skillhost.py /opt/skillkit/
ENV RCB_SKILL_PORT=8765 RCB_SKILLKIT=/opt/skillkit/skillhost.py
WORKDIR /app
