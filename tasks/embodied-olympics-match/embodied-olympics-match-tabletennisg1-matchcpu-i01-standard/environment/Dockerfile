# The agent's container: the tabletennis_g1 seat image (Embodied Olympics' generated seat of
# tabletennis_g1-match-wallclock-program-engineer-standard: the `game` client and `ro_client`, the rules, the G1
# toolkit under /opt/ro, the training kit /opt/train, the practice sandbox /opt/practice), prebuilt.
FROM ghcr.io/mll-lab-nu/efe:embodied-olympics-match-tabletennisg1-seat-0.1.1@sha256:3b393ae5e79e383ac0de2ffad81f0ec946df5ca32ac125baeb7193a85b31cd15
ENV SIM_URL=http://localhost:8000 PRACTICE_URL=http://localhost:8100 SEAT=A
# Embodied First Exam: the verdict ends the session (match_end.sh, the container's entrypoint).
COPY match_end.sh /opt/efe/match_end.sh
ENTRYPOINT ["/opt/efe/match_end.sh"]
WORKDIR /app
