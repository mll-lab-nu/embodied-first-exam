FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="8e8a7476535966fa96699cf00881ae68aa57a054ec75a6504a8b224291c65c1a"
LABEL roboengineer.instance_sha256="a624eb859de9e7b51dcb1527fcc4e40292ef4cd2dd1df78c26773834fc966857"
COPY payload-8e8a7476535966fa96699cf00881ae68aa57a054ec75a6504a8b224291c65c1a/ /tests/
RUN echo 'a624eb859de9e7b51dcb1527fcc4e40292ef4cd2dd1df78c26773834fc966857  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo 'a624eb859de9e7b51dcb1527fcc4e40292ef4cd2dd1df78c26773834fc966857  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo '737120bed19271d99b89951fc6fc58f9929e4faf6a90e315966a632f59c8bb78  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
