FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="8d40acf45e04f20e07bef9982b1ea687cec0e7f2b060aa5851b425835e994453"
LABEL roboengineer.instance_sha256="e7032816b31bc45e519af1a93a64c51926eb14711e5e932329d1f806fdfe7fea"
COPY payload-8d40acf45e04f20e07bef9982b1ea687cec0e7f2b060aa5851b425835e994453/ /tests/
RUN echo 'e7032816b31bc45e519af1a93a64c51926eb14711e5e932329d1f806fdfe7fea  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo 'e7032816b31bc45e519af1a93a64c51926eb14711e5e932329d1f806fdfe7fea  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo 'b9d220f8bfa51da23150d0b3f645549a83549ab0ea85d4ae4ea710408d8a3ea6  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
