FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="aaac1abc2a86eaec2d3750154cf7d98fb8036722bed3fab3ccd677a68748181a"
LABEL roboengineer.instance_sha256="0ca3b164fcad8801dda9677c35dcbe7d3e5a51086f3976d8b23c28b8d8e24498"
COPY payload-aaac1abc2a86eaec2d3750154cf7d98fb8036722bed3fab3ccd677a68748181a/ /tests/
RUN echo '0ca3b164fcad8801dda9677c35dcbe7d3e5a51086f3976d8b23c28b8d8e24498  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo '0ca3b164fcad8801dda9677c35dcbe7d3e5a51086f3976d8b23c28b8d8e24498  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo '32bc9b4eed7cf2c9fa7bad33ed54c6d73701bc43dc8a4da426613e2e34eaac91  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
