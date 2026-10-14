FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="97f7964cc8cdb614b2dbd950902c4551937023f86bab97640571a93d56be1498"
LABEL roboengineer.instance_sha256="a7f19a1f0d06f302cef44b6705347faf41298505bc2a19c26731c21b8648e130"
COPY payload-97f7964cc8cdb614b2dbd950902c4551937023f86bab97640571a93d56be1498/ /tests/
RUN echo 'a7f19a1f0d06f302cef44b6705347faf41298505bc2a19c26731c21b8648e130  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo 'a7f19a1f0d06f302cef44b6705347faf41298505bc2a19c26731c21b8648e130  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo 'a1b5f682f7734fcaf1e29c866a9c9d1773a4edc4a06e10e151122220fb9eb385  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
