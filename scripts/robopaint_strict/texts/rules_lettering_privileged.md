## Process rules
Letter the word with pen strokes, the way a scribe writes it: each stroke of a letter is a pass of the pen along it, its width
coming from the pen (a broad nib: its angle and the direction of travel; a pointed pen: the pressure); going over a stroke again
is fine. Colouring in or filling the letters' shapes, zigzag or serpentine fills (back-and-forth passes across a stroke), and
contour-offset fills are not allowed and fail the task, even when the sheet matches the picture. The grader checks this on the
replayed trajectory with two numbers you can compute yourself; only inked strokes on the main sheet count (the practice sheet is
free):
- `path_mm`: the total length of the pen tip's path while it presses on the main sheet with ink (all strokes together, sampled
  at every physics step);
- `mark_width_mm`: the average width of your marks = the area each stroke inks on its own (its own mark, ink coverage ≥ 0.5;
  where different strokes overlap, each counts its own), summed over the strokes, divided by `path_mm`.

**Colouring in = `path_mm` > {{MAX_PATH_MM}} mm and `mark_width_mm` < {{MIN_MARK_WIDTH_MM}} mm** (a long path of thin marks): it
fails the task. Our reference solution writes this word with `path_mm` {{REF_PATH_MM}} mm and `mark_width_mm`
{{REF_MARK_WIDTH_MM}} mm; the limits are {{PATH_FACTOR}} times its path (rounded up) and {{MARK_FACTOR}} times its mark width
(rounded down). A pressed pen, even over a stroke again, keeps the marks wide enough, and a light hand on a short path stays
under the path limit: both are fine.

**Success iff the picture rule above holds and the run is not colouring in.** `final_reward` = the continuous score above, ×
min(1, {{MAX_PATH_MM}} / `path_mm`) when it is colouring in. `s.score()` reports `path_mm`, `mark_width_mm`, `max_path_mm`,
`min_mark_width_mm`, `colour_in`, `image_success` (the picture rule alone), `strict_ok` (the process rule) and `success` (both);
`s.strokes()` holds each stroke's samples and its own mark.
