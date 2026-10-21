# ABC Sim task (privileged): abc_sim on MuJoCo 3.6.0 (images/abc-sim/: the simulator, the scenes' assets and the
# benchmark's tooling at /opt/abc-tools), and the task's frozen instance. Cameras render over EGL on the GPU.
FROM ghcr.io/mll-lab-nu/efe:abc-sim-0.1.0
COPY instance.npz /app/instance.npz
RUN mkdir -p /app/output
WORKDIR /app
