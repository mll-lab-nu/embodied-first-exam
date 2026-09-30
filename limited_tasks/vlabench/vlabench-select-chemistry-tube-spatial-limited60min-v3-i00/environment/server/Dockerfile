FROM ghcr.io/jameskrw/rcb-vlabench:0.1.1
COPY . /private/
RUN mkdir -p /trusted && tar xzf /private/backend.tar.gz -C /trusted && ln -s /opt/VLABench/VLABench/assets /trusted/VLABench/assets
ENV PYTHONPATH=/private:/trusted:/opt/VLABench:/opt/rrt-algorithms
RUN mkdir -p /recorded /run/limited && chown 65532:65532 /recorded /run/limited
WORKDIR /private
USER 65532:65532
CMD ["python", "server.py"]
