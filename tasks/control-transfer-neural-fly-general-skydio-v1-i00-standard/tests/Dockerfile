FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="0f87634fc56894c79402b927d32bbd652be4b56d2b213b7d2b2df3c400bbc14f"
LABEL roboengineer.instance_sha256="a478623aea19f5ec780167206f307b6eb05a29d8fe97962bea00ff985bfe1ae8"
COPY payload-0f87634fc56894c79402b927d32bbd652be4b56d2b213b7d2b2df3c400bbc14f/ /tests/
RUN echo 'a478623aea19f5ec780167206f307b6eb05a29d8fe97962bea00ff985bfe1ae8  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo 'a478623aea19f5ec780167206f307b6eb05a29d8fe97962bea00ff985bfe1ae8  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo '1b97ca9a590d0aa35f3ee799d13d342d559472a12357609469a38f2b807f0d29  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
