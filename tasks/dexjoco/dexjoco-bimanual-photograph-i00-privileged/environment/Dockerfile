# Base image = DexJoCo on MuJoCo 3.4.0 (images/dexjoco/). Everything task-specific is copied here. CPU only.
FROM ghcr.io/mll-lab-nu/efe:dexjoco-0.1.2
COPY instance.npz /app/instance.npz
COPY --from=ghcr.io/mll-lab-nu/efe:dexjoco-files-0.1.1@sha256:7976cf6afa2103ded00826a3e82239e7e5e84fcc9a9380640ef40f8d9bcd80b2 /privileged/environment/rcb_dexjoco.py /opt/tools/rcb_dexjoco.py
ENV PYTHONPATH=/opt/tools
# the simulation's result depends on OpenBLAS's thread count below 4; 4 is what the verifier runs with (tasks/dexjoco/README.md)
ENV OPENBLAS_NUM_THREADS=4
RUN mkdir -p /app/output
WORKDIR /app
