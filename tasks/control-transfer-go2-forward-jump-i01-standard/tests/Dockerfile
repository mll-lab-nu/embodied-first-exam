FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="9d45e8be1355af15285de09d70435691deddc594806255c6c7aceb988c519f91"
LABEL roboengineer.instance_sha256="95085e812ca4f37c9cc9e05005fe83a47cc72a72f59b35c66f48d5dd8ab022cb"
COPY payload-9d45e8be1355af15285de09d70435691deddc594806255c6c7aceb988c519f91/ /tests/
RUN echo '95085e812ca4f37c9cc9e05005fe83a47cc72a72f59b35c66f48d5dd8ab022cb  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo '95085e812ca4f37c9cc9e05005fe83a47cc72a72f59b35c66f48d5dd8ab022cb  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo '5ddac4200d02feb42e04d9004b9bb2079cc9cd09aef81f5dcec6001ca700946f  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
