**RoboPaint-strict** (docs/benchmarks/robopaint-strict.md): the RoboPaint task `{{SRC}}-standard` with process rules on top of its
picture rule, so that the exemplar has to be made with strokes rather than coloured in: {{RULES}} Same scene, frozen instance
(the rules added to its `target.success`), picture, service and reference solution; the collect hook's replays apply the rules
with the graders' `rcb_brush_strict.py`.
