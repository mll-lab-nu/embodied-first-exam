"""python -m pipeline <step> [options]   (run from analysis/cross-bench/review/; `<step> -h` for its options)

Steps in order (README.md has the table of inputs and outputs):
  sample    choose the trials                       -> sample.json
  prep      events, script facts, evidence packets  -> events/, facts/, packet/
  looks     images the agent received               -> looks/
  codes     code tables from the report's codebook  -> prompts/codes.json, prompts/recap.md
  annotate  run the recap prompt per trial (model)  -> recaps/
  check     check quotes and order, add time codes  -> verified_recaps/
  sync      map wall clock to the graded replay     -> service/ (--fetch), videomap/
  video     annotated whole-trial video             -> fullvideo/
  pages     one review page per trial               -> pages/
  summary   tables over all trials                  -> stdout or --out
  search    full-text search of one trial (used by the annotator)"""
import importlib, sys

STEPS = {"sample": "sample", "prep": "prep", "looks": "looks", "codes": "codes", "annotate": "annotate", "check": "check",
         "sync": "sync", "video": "fullvideo", "pages": "pages", "summary": "summary", "search": "search"}

if len(sys.argv) < 2 or sys.argv[1] not in STEPS:
    sys.exit(__doc__)
importlib.import_module(f"pipeline.{STEPS[sys.argv[1]]}").main(sys.argv[2:])
