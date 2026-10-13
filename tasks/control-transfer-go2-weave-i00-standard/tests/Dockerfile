FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="01dd4151744bdd2102831e6da53aa2d71aec8fc1a1f9d90ad5a00c5b49fbe555"
LABEL roboengineer.instance_sha256="fe9c4090785a13e72a420d8382e7e488f48c9b496ad9b885a1dc93ef27185f4f"
COPY grade.py test.sh instance.json rcb_limits.py rcb_limits.json /tests/
RUN echo 'fe9c4090785a13e72a420d8382e7e488f48c9b496ad9b885a1dc93ef27185f4f  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo 'fe9c4090785a13e72a420d8382e7e488f48c9b496ad9b885a1dc93ef27185f4f  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo '5cfd5370a76a8e0b0db0e96a05b33a91fd55c5fc3b49a9cee0626140e2956896  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
