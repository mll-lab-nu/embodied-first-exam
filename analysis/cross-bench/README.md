# Cross-bench analysis

Only code, prompts and the configuration the tools read are in git (see `.gitignore`; this repo is public).
Everything else stays local.

| path | content | in git |
|---|---|---|
| `tools/` | the analysis pipeline and the site builder | yes |
| `tools/viz/` | annotated replays of single trials (`tools/viz/README.md`) | yes |
| `review/` | trial review: recap prompt and checks, annotated whole-trial video, review platform (`review/README.md`) | yes |
| `meta/prompts/`, `meta/DESIGN.md` | reviewer prompts, method | yes |
| `meta/codebook.json`, `meta/site.json`, `meta/bench_reasons.json` | configuration the tools read | yes |
| `annot/`, `reviews/`, `findings/`, `notes/`, `data/`, `ledger.csv`, `retired/` | labels, reviews, report text, tables | no |
| `refs/`, other `meta/*` (`HANDOFF.md`, `PLAN.md`, ...) | meeting notes, working notes | no |

Local data: raw trial cache `/data/pingyue/cross-bench/raw`, compressed media `/data/pingyue/cross-bench/media`,
annotated replays `/data/pingyue/cross-bench/viz`, trial review work directory `/data/pingyue/cross-bench/pilot-hl`, site mirror `~/Work/cross-bench-artifact`.
