FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="c2526c15efc8340c3bcbcf647299f77b6d28d0f59abe175703eb8a577ab18134"
LABEL roboengineer.instance_sha256="b1f4286ff9986505820598ed877a7c6e32498558facfa55083ef66ce01e67447"
COPY grade.py test.sh instance.json rcb_limits.py rcb_limits.json /tests/
RUN echo 'b1f4286ff9986505820598ed877a7c6e32498558facfa55083ef66ce01e67447  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo 'b1f4286ff9986505820598ed877a7c6e32498558facfa55083ef66ce01e67447  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo '5294e669018d828f37812fa5f1293f06575f7474b16633a236dfc1478a3762d1  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
