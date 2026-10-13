FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="a85cd5813a1c847e101962ab22d77b63352e0c749ee350d1a0c31eedd92cd482"
LABEL roboengineer.instance_sha256="cca60b2ae312e060d8c5c95e181f70db674a2ca02a13e37b9714959bc46e9135"
COPY grade.py test.sh instance.json rcb_limits.py rcb_limits.json /tests/
RUN echo 'cca60b2ae312e060d8c5c95e181f70db674a2ca02a13e37b9714959bc46e9135  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo 'cca60b2ae312e060d8c5c95e181f70db674a2ca02a13e37b9714959bc46e9135  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo 'e10a8bcfa78494b79acc80f4089b5680a568018875a58a5dcd5be11d62431510  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
