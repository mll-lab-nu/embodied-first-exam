FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="7b07e5150b83e1a36dbe7ce0c036540af076eb53242000f9af8a2b73a21fce67"
LABEL roboengineer.instance_sha256="b5a406fca83593e7cbdef2d7122f07ed969abaea477d3af68182d2a43d83b783"
COPY grade.py test.sh instance.json rcb_limits.py rcb_limits.json /tests/
RUN echo 'b5a406fca83593e7cbdef2d7122f07ed969abaea477d3af68182d2a43d83b783  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo 'b5a406fca83593e7cbdef2d7122f07ed969abaea477d3af68182d2a43d83b783  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo '16731e147e7e2ddcef5cfcab95806c786ac3ebf23a9181332d6d00ace82983a0  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
