## Process rules
Paint with brush strokes, the way a person paints: each stroke is one sweep of the loaded brush, pressed for the width you want.
Colouring in or filling areas with a thin line, zigzag or serpentine fills, and contour-offset fills (paths that circle round and
round inside an area) are not allowed and fail the task, even when the sheet matches the picture. The grader checks this on the
replayed trajectory with two numbers you can check yourself; only painted strokes on the main sheet count (the practice sheet is
free):
- **Paint path budget: `path_mm` ≤ {{MAX_PATH_MM}} mm.** `path_mm` is the total length of the brush tip's path while it presses
  on the main sheet with paint (all strokes together, sampled at every physics step). The strokes of our reference solution add up
  to {{REF_PATH_MM}} mm; the budget is {{PATH_FACTOR}} times that, rounded up.
- **Strokes are sweeps: `scribble_share` ≤ {{MAX_SCRIBBLE_SHARE}}.** A stroke's scribble ratio is its length divided by the
  diagonal of its bounding box on the sheet (taken as at least {{SCRIBBLE_MIN_MM}} mm): about 1 for a straight or curved sweep,
  2 for a sweep out and back along the same line, more for a zigzag, a back-and-forth fill, a spiral or a loop. `scribble_share`
  is the share of `path_mm` in strokes whose ratio is above {{MAX_SCRIBBLE}}.

**Success iff the picture rule above holds and both process rules hold.** `final_reward` = the continuous score above ×
min(1, {{MAX_PATH_MM}} / `path_mm`) × (1 − `scribble_share` when the second rule fails). `s.score()` reports `path_mm`,
`max_path_mm`, `scribble_share`, `scribble_max` (the largest ratio of a stroke), `longest_stroke_mm`, `image_success` (the picture
rule alone), `strict_ok` (the process rules) and `success` (all).
