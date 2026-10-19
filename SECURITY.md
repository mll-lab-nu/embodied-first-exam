# Security policy

Please do not report security problems in public issues or pull requests.

E-mail **embodied-first-exam@gmail.com** with the subject "Security", or use GitHub's private vulnerability reporting
(the repository's Security tab, "Report a vulnerability"). Include what is affected, how to reproduce it and its impact.
We answer within a week.

In scope:
- **Isolation of grading.** A way for the agent under test to change or forge its own result: reach the verifier's
  sandbox, the standard modes' simulator sidecar or the declared artifacts after submission, or read a task's reference
  solution or its source (docs/protocol/README.md Appendix H). These are the bugs that matter most for the exam.
- **The tooling in this repository**: the Harbor wrapper (`scripts/efe.py`), the optional usage gateway
  (`scripts/usage_gateway/`), the base images under `images/` and the GitHub workflows.

A task an agent can solve by a shortcut that does not break isolation (a weak success predicate, a leaked hint) is
a task bug: report it in a normal issue (collaborators may open a pull request; CONTRIBUTING.md, "Task fix").
