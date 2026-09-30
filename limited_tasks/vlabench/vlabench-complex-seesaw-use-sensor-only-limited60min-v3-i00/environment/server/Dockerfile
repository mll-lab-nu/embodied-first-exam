FROM ghcr.io/jameskrw/rcb-vlabench:0.1.1
COPY . /private/
ENV PYTHONPATH=/private:/trusted:/opt/VLABench:/opt/rrt-algorithms
RUN mkdir -p /recorded /run/limited && chown 65532:65532 /recorded /run/limited
WORKDIR /private
USER 65532:65532
CMD ["python", "server.py"]
