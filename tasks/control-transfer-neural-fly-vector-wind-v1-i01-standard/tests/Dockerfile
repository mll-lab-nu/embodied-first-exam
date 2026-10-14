FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="7369f4803c42c3657bf02dd8940c553d3e15d280675013c7d21d0b43b0b46bfa"
LABEL roboengineer.instance_sha256="470689a1804fd87ccf7863fec3e2b4f3ede8cd4d42b2a1d71f390b9304454451"
COPY grade.py test.sh instance.json rcb_limits.py rcb_limits.json /tests/
RUN echo '470689a1804fd87ccf7863fec3e2b4f3ede8cd4d42b2a1d71f390b9304454451  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo '470689a1804fd87ccf7863fec3e2b4f3ede8cd4d42b2a1d71f390b9304454451  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo '2e1f452c96eb80d65d2bf8b2f62cde820b097a080242ff1fd7c9a6a0dca35231  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
