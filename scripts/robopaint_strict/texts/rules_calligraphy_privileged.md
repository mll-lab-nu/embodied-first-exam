## Process rules
Write the character with brush strokes, the way a person writes it: each stroke of the exemplar is written along its length,
with the brush pressed for the stroke's width (vary the press where the width changes); going over a stroke again is fine.
Colouring in or filling the shapes, zigzag or serpentine fills, and contour-offset fills (paths that go round and round inside a
shape) are not allowed and fail the task, even when the sheet matches the picture. The grader checks this on the replayed
trajectory with two numbers you can compute yourself; only inked strokes on the main sheet count (the practice sheet is free):
- `path_mm`: the total length of the brush tip's path while it presses on the main sheet with ink (all strokes together, sampled
  at every physics step);
- `mark_width_mm`: the average width of your marks = the area each stroke inks on its own (its own mark, ink coverage ≥ 0.5;
  where different strokes overlap, each counts its own), summed over the strokes, divided by `path_mm`.

**Colouring in = `path_mm` > {{MAX_PATH_MM}} mm and `mark_width_mm` < {{MIN_MARK_WIDTH_MM}} mm** (a long path of thin marks): it
fails the task. Our reference solution writes this exemplar with `path_mm` {{REF_PATH_MM}} mm and `mark_width_mm`
{{REF_MARK_WIDTH_MM}} mm; the limits are {{PATH_FACTOR}} times its path (rounded up) and {{MARK_FACTOR}} times its mark width
(rounded down). A pressed brush, even over a stroke again, keeps the marks wide enough, and a light hand on a short path stays
under the path limit: both are fine.

**The stroke cap counts strokes as they are written, not contacts** (this refines "one continuous contact is one stroke"
above). A contact is cut into two strokes wherever the brush moves more than {{STROKE_GAP_MM}} mm along the main sheet without
marking it (its mark narrower than {{MARK_MIN_WIDTH_MM}} mm: a press too light to ink), and a stroke longer than
{{MAX_STROKE_PATH_MM}} mm of path counts as one stroke per started {{MAX_STROKE_PATH_MM}} mm ({{STROKE_PATH_FACTOR}} times our
reference solution's longest stroke, {{REF_LONGEST_STROKE_MM}} mm, rounded up). Pieces joined by a touch too light to ink are
therefore separate strokes, and one contact held down to write and re-write for a long time counts as several; a stroke
written with the brush down and lifted at its end is one. **Strokes are sweeps:** at most {{SCRIBBLE_SHARE_PCT}} % of
`path_mm` may lie in strokes whose path is longer than {{MAX_SCRIBBLE}} times the diagonal of their bounding box (taken as at
least {{SCRIBBLE_MIN_MM}} mm): back-and-forth, zigzag, spiral or looping fills inside one stroke fail (our reference solution's
strokes stay under 5 times).

**Success iff the picture rule above holds, the run is not colouring in, the counted strokes are within the cap and the strokes
are sweeps.** `final_reward` = the continuous score above, ×
min(1, {{MAX_PATH_MM}} / `path_mm`) when it is colouring in, × (1 − that share) when the strokes are not sweeps, and with the
cap's scaling taken on the counted strokes. `s.score()` reports `path_mm`, `mark_width_mm`, `max_path_mm`,
`min_mark_width_mm`, `colour_in`, `n_strokes_counted`, `n_marked_pieces`, `longest_counted_stroke_mm`, `max_stroke_path_mm`,
`strokes_counted_ok`, `scribble_share`, `scribble_ok`, `image_success` (the picture rule alone), `strict_ok` (the process
rules) and `success` (both); `s.strokes()` holds each stroke's samples (the mark's width is the fourth column, in m) and its
own mark.
