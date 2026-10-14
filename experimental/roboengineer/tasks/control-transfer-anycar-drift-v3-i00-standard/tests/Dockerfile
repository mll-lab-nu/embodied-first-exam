FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="ad7b9baf44791ac2850fdd6ff820769ac81cc3167749049066e47480ba87aa4f"
LABEL roboengineer.instance_sha256="2de6fb2ea39d0293b13d58b5ed8ef416c1bce367907b3e28049759a2f0f9e772"
COPY payload-ad7b9baf44791ac2850fdd6ff820769ac81cc3167749049066e47480ba87aa4f/ /tests/
RUN echo '2de6fb2ea39d0293b13d58b5ed8ef416c1bce367907b3e28049759a2f0f9e772  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo '2de6fb2ea39d0293b13d58b5ed8ef416c1bce367907b3e28049759a2f0f9e772  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo '1ec439f664c9731cd43183e1af5924796c9b58b42aace8d042bec246cd92cd37  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
