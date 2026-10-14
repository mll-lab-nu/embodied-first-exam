FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL roboengineer.verifier_inputs_sha256="1e9c0b790fba9d33dda90ee2bcd48b319e1a981acd1215339d5e6d14b72b6c1f"
LABEL roboengineer.instance_sha256="a408ef7a7e3d0ceb32e1dd64c1b6907179db45b45e19e508c4f1605961aa5fa1"
COPY grade.py test.sh instance.json rcb_limits.py rcb_limits.json /tests/
RUN echo 'a408ef7a7e3d0ceb32e1dd64c1b6907179db45b45e19e508c4f1605961aa5fa1  /tests/instance.json' | sha256sum -c - && chmod +x /tests/test.sh
RUN echo 'e2459a0520c1072df9daf2d6a6caccb3695b5589464eeacd18dccf1c09f18273  /tests/grade.py' | sha256sum -c - && echo '98c0880bb8118c172f768073271254c7210eb71855bab44b86b28af139490a28  /tests/test.sh' | sha256sum -c - && echo 'a408ef7a7e3d0ceb32e1dd64c1b6907179db45b45e19e508c4f1605961aa5fa1  /tests/instance.json' | sha256sum -c - && echo '68e07a860bf218cd7c9c2bfe1aaa4801d0ee68e7f8c789aefa3b1ebc4740d809  /tests/rcb_limits.py' | sha256sum -c - && echo '7f0638ad821d486257b340378b9cb0079caa321272195910c4b4ac2593b34595  /tests/rcb_limits.json' | sha256sum -c -
# resource limits: the verifier step and its copy of the limits (docs/PROTOCOL.md §2.10) # rcb-monitor
COPY rcb_limits.py rcb_limits.json /tests/
