FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="b74f26f1a3e0ffd1ffeb6a6f208c7c473535ed6bc621cb3469402c907d93c76f"
LABEL roboengineer.instance_sha256="4478b101e571b8cfbc9b96bf2e33afc50e983df3c1a812448d2e9ed5b2f042e6"
COPY grade.py test.sh instance.json rcb_limits.py rcb_limits.json /tests/
RUN echo '4478b101e571b8cfbc9b96bf2e33afc50e983df3c1a812448d2e9ed5b2f042e6  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo '4478b101e571b8cfbc9b96bf2e33afc50e983df3c1a812448d2e9ed5b2f042e6  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo '767125c7fe97dff1cca80d158b90956e14d681655c1b967c8af6e20fa631ed23  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
