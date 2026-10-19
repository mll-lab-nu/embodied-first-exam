# Base image = RoboLab v0.3.1 + Isaac Lab 2.3.2 / Isaac Sim 5.1 + RoboLab's asset library (see images/robolab/).
# Everything task-specific is copied here.
FROM ghcr.io/mll-lab-nu/efe-private:robolab-0.1.2
# RoboLab's repository ships one recorded episode (examples/recorded_data/RubiksCubeAndBananaTask: the actions of a successful
# run, replayed by examples/run_recorded.py): a solution of one of these tasks within the agent's reach (PROTOCOL §2.7).
# Nothing at run time reads it (only that example script does); the agent's image does not keep it.
RUN rm -rf /opt/robolab/examples/recorded_data
COPY instance.json /app/instance.json
COPY --from=ghcr.io/mll-lab-nu/efe-private:robolab-files-0.1.0@sha256:4e656f245a9e7eb7c55bc5f2c94342813f48c7ea868be8f08aab2ca2b5dee932 /rcb_robolab.py /opt/tools/rcb_robolab.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
