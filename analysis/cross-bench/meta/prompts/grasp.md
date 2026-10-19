# Grasp failure subtype prompt (prompt id `grasp-1`)

For failed trials whose review lists `grasp-contact` (primary or secondary), say **how** the grasp or contact failed,
from the review text (decisive error, evidence, story tail, headline). One label per trial, plus up to one extra.

Subtypes:
- `miss`: the fingers closed on nothing or on the wrong spot (object not between the fingers; position or hand-geometry error)
- `push-away`: closing or approaching pushed, knocked or tipped the object away
- `slip-lift`: the object was held, then slipped out while lifting or tilting
- `slip-carry`: the object slipped or dropped during transport or a base move
- `release`: placing or releasing went wrong (dropped too high, released before support, stuck on the fingers)
- `cannot-hold`: the hand cannot hold it at all (too wide, too heavy, too thin, no friction, force limit)
- `tool-use`: a held tool or object did not make the intended contact (pushing, scooping, wiping, inserting)
- `other`: none of the above (say what)

Output one file per trial: `/data/pingyue/rcb-wt/xbench-analysis/analysis/cross-bench/annot/grasp/<key>.json`
`{"key": "...", "prompt": "grasp-1", "subtype": "<code>", "also": "<code or empty>", "why": "一句中文：发生了什么（引用分析里的时刻或事实）"}`.
Never use the word "oracle". Reply with one line: files written and a count per subtype.
