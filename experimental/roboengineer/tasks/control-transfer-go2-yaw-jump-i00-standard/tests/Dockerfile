FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="acbce9517c445651afd4a7f84b3f7ffc5b98aeba95aef0748564602e077a9180"
LABEL roboengineer.instance_sha256="a3eeac70b3cd0b330a4995e810ed1c8ab36597814c88abcbd9ef9852a00e7397"
COPY payload-acbce9517c445651afd4a7f84b3f7ffc5b98aeba95aef0748564602e077a9180/ /tests/
RUN echo 'a3eeac70b3cd0b330a4995e810ed1c8ab36597814c88abcbd9ef9852a00e7397  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo 'a3eeac70b3cd0b330a4995e810ed1c8ab36597814c88abcbd9ef9852a00e7397  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo '0ad560e4d75fc24bb4884a18b2e0f9fa98ca00d2e1f04dc461a1aa0b50c5b352  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
