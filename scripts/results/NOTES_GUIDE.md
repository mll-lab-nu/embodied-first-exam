# Writing a run's analysis (`<trial>/report/notes.md`)

The results pages (`build.py`) show this file as the run's analysis: its first paragraph is the verdict at the top of
the task page, the rest the analysis panel (`data.notes_of` parses both, and the phase table below). Humans or agents
write it after reading the run; everything else on the pages is measured.

1. `python3 scripts/results/digest.py jobs/<job>` puts each trial on one page, `<trial>/report/digest.md`: the numbers,
   the episodes (limited) or the agent's `NOTES.md` and `gen.py` (full), the leak-check flags, and everything the agent
   said and ran, in order, with times.
2. Write `notes.md` from it as below, plus the one-line English note for `runs.csv`'s `note` column.
3. `python3 scripts/results/build.py` shows it, and says which README cells no longer match `runs.csv`.

## Rules
- Chinese prose; identifiers, commands and quotes of the agent stay in English.
- Only what the sources show, and every number from them: the digest first, then `report/summary.json`,
  `agent/trajectory.json`, the agent's files, and images if you can view them (`report/episodes/*.png`,
  `report/agent_views/`, `verifier/replay.last.png`).
- Look at the leak-check flags and say what the agent actually read (upstream source, our tooling, the network).
- An episode that `failed` is a fall only if the robot was down: the digest's `head_h` (the head above the lower
  foot at the end) of 1 m or more means it was still up when the episode ended (it crossed the task's end line in a
  crouch, a lean or a seat on the floor, or a tool or an object dropped), and a robot lying with its pelvis above
  the fall line runs on to the step limit. `progress` says how far a multi-stage task got.
- Never guess at the reward formula's internals, and do not discuss whether the task is solvable.
- About 30–45 lines of plain Markdown: headings, bullets, **bold**, `code`, tables if needed.

## Layout
Limited mode only, first: a phase table, which colours the robot timeline. 3–6 consecutive phases by what the agent
was doing; inclusive episode ranges covering 0 to the last episode; names of at most 6 Chinese characters:

    <!-- phases
    0-10 标定
    11-14 站姿
    15-49 步态加 IMU
    50 被评分
    -->

Then, both modes:

    **一句话**：<2–3 sentences: the approach, the result (graded return against the bar and the all-zero action),
    the main reason it passed or failed, time used and cost.>

    ### 做了什么
    - **<episodes or minutes>（<how long>，<phase>）**：what it tried, what it saw (its own words, in English quotes),
      what it concluded. 4–8 bullets, in time order.

    ### 被评分的那一段        (full mode: ### 交的轨迹)
    - limited: what the last (graded) episode ran, how many steps, how it ended, its return.
    - full: how the submitted trajectory was made (read gen.py), its length, the replayed return; what its NOTES.md claims.

    ### 为什么没过            (or: ### 怎么过的)
    - 2–4 bullets, each with its evidence.

    ### 和另一种模式对比       (when the task has a run in the other mode)
    - 1–3 bullets: approach, return, time, cost.

The `runs.csv` note: under 150 characters, the approach and the outcome, e.g. "stance plus small IMU-corrected gait;
never stepped forward; graded ep fell at step 537".
