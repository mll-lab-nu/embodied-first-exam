# EmbodiedSWE base image (images/embodiedswe/: RoboLab's Isaac Sim 5.1 / Isaac Lab 2.3.2 recipe + robobench at a pinned
# commit, scrubbed, + its assets by sha256); built locally, not published (images/embodiedswe/BUILD_ONLY). The tooling
# comes from the files image (images/embodiedswe-files/, source embodied_first_exam/benchmarks/embodiedswe/).
FROM ghcr.io/mll-lab-nu/efe-private:embodiedswe-0.3.0
COPY --from=ghcr.io/mll-lab-nu/efe:embodiedswe-files-0.4.0@sha256:39e678fbc46858843efd77c27fd11fe57d6bd768af11e0c6ce37ad3a84f52351 /rcb_embodiedswe.py /esw_proxy.py /esw_submit.py /opt/efe/
COPY instance.json /app/instance.json
RUN ln -s /opt/efe/esw_submit.py /usr/local/bin/submit && mkdir -p /app/output
WORKDIR /app
