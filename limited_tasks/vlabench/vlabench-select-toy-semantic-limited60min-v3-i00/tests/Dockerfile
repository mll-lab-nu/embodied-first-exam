FROM ghcr.io/jameskrw/rcb-vlabench:0.1.1
COPY . /tests/
RUN mkdir -p /trusted && tar xzf /tests/backend.tar.gz -C /trusted && ln -s /opt/VLABench/VLABench/assets /trusted/VLABench/assets
ENV PYTHONPATH=/tests:/trusted:/opt/VLABench:/opt/rrt-algorithms
WORKDIR /tests
