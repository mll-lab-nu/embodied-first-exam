# topogym

Harbor tasks where a coding agent controls a simulated TopoGym robot through Python primitives and must leave one
replayable trajectory for a frozen scene instance (`topogym-<family>-i<NN>`), or drives it as a service through the
`rcb-limited/2.2` client (`topogym-<family>-i<NN>-limited`). See `docs/rcb/README.md` for the runs and
`docs/rcb/PROTOCOL.md` for scoring. The protocol v1.0 tier tasks are `topogym-<family>-<tier>-i00-privileged` and their
standard-mode twins `-standard` (`eai-standard/2.2`): `docs/rcb/benchmarks/topogym.md`.
