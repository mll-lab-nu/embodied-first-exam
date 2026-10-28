# gemini: twenty paired trajectory cards

Step numbers below are one-based decisions. Observation IDs are zero-based. Selection is diagnostic, not prevalence-weighted.

## C061: gemini / codex only

Task: scene `102344529`, episode `12`, target **chair**. Shard `shard-0072`.

Exact common action prefix: **3** decisions. The next action is the first behavioral divergence; it is not automatically the cause of the outcome.

| Harness | Terminal fact | Actions | Requests | Sit calls | Final distance (m) | Active stop | Target ever visible (GT) | Collision-step fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Codex | Success | 33 | 35 | 0 | 0.000 | True | True | 0.344 |
| Pi | Stopped outside threshold | 12 | 13 | 0 | 1.277 | True | False | 0.000 |


**Codex, divergence decision 4**: `Turn<left><90>`. Visible-state claim: “Facing the corner of the wooden wall. The doorway to the wooden-floored room is on the left. The target is not in direct view yet. The near-body lane is clear.”

**Codex, final decision 33**: `Stop/Stand`. Visible-state claim: “The body is directly touching the back of the brown armchair with zero distance. The target chair is visible right in front of the body. Calling stand to finish the episode.”

<details><summary>Codex complete action chain (consecutive repeats compressed)</summary>

`Turn<right><90>` ×2 → `Turn<left><120>` → `Turn<left><90>` → `Turn<left><60>` → `Turn<right><70>` → `Turn<right><30>` → `Walk<forward><fast>` → `Turn<right><25>` ×2 → `Side step<left><0.15>` ×2 → `Turn<right><25>` → `Walk<forward><fast>` → `Turn<left><30>` → `Walk<forward><fast>` → `Turn<left><80>` → `Turn<left><30>` → `Walk<forward><fast>` ×4 → `Side step<right><0.30>` → `Walk<forward><fast>` → `Side step<right><0.40>` ×2 → `Walk<forward><fast>` ×3 → `Turn<right><20>` → `Turn<right><25>` → `Walk<forward><slow>` → `Stop/Stand`

</details>

Codex source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-codex-copilot-gemini-argon-fullval-r2-20261018/results/shard-0072/102344529_ep12_chair/rollout_00/experiment_runs/run_2e91125e62b9480a89ef09cd2bc9e006/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

**Pi, divergence decision 4**: `Turn<left><80>`. Visible-state claim: “Facing the corner between the doorway on the left and the garage door on the right. Near-body lane is clear. Target chair is not visible yet.”

**Pi, final decision 12**: `Stop/Stand`. Visible-state claim: “Facing the wooden bench/chair directly in front of the body, with the body touching the target at zero distance. Near-body lane forward is occupied by the target.”

<details><summary>Pi complete action chain (consecutive repeats compressed)</summary>

`Turn<right><90>` ×2 → `Turn<left><120>` → `Turn<left><80>` → `Turn<left><60>` → `Turn<right><80>` → `Turn<right><30>` → `Side step<left><0.40>` → `Walk<forward><normal>` → `Walk<forward><fast>` → `Turn<left><80>` → `Stop/Stand`

</details>

Pi source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-pi-copilot-gemini-argon-fullval-r2-20261018/results/shard-0072/102344529_ep12_chair/rollout_00/experiment_runs/run_e8c484d00bfc4d8babc4f8a2b73f4e03/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

Saved-image review sheet: [four recorded views](../assets/C061_sheet.jpg). These are existing observations, not a replay.

Interpretation boundary: distance/contact results are evaluator facts. The quoted visible-state descriptions are model claims. Images, orientation, contact progression, and recovery behavior must be read together before assigning a causal failure label.

---

## C062: gemini / codex only

Task: scene `106366410_174226806`, episode `29`, target **toilet**. Shard `shard-0743`.

Exact common action prefix: **0** decisions. The next action is the first behavioral divergence; it is not automatically the cause of the outcome.

| Harness | Terminal fact | Actions | Requests | Sit calls | Final distance (m) | Active stop | Target ever visible (GT) | Collision-step fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Codex | Success | 50 | 51 | 3 | 0.022 | True | True | 0.510 |
| Pi | No Sit executed | 100 | 110 | 0 | 3.954 | True | False | 0.263 |


**Codex, divergence decision 1**: `Turn<left><90>`. Visible-state claim: “Facing a kitchen countertop with knife blocks, bottles, and a range hood; the toilet is not visible and the counter blocks the path directly ahead.”

**Codex, final decision 50**: `Stop/Stand`. Visible-state claim: “Fully seated on the toilet facing the bathroom vanity; submitting the final seated pose.”

<details><summary>Codex complete action chain (consecutive repeats compressed)</summary>

`Turn<left><90>` ×2 → `Turn<right><75>` → `Turn<right><20>` → `Walk<forward><fast>` ×3 → `Turn<left><80>` → `Walk<forward><fast>` ×3 → `Turn<right><25>` → `Walk<forward><fast>` ×5 → `Turn<left><80>` → `Turn<left><45>` → `Side step<right><0.30>` → `Walk<forward><fast>` ×3 → `Turn<right><75>` → `Side step<left><0.25>` → `Walk<forward><fast>` ×3 → `Turn<left><80>` → `Walk<forward><fast>` → `Side step<right><0.30>` → `Side step<right><0.20>` → `Walk<forward><fast>` → `Turn<right><75>` → `Walk<forward><fast>` → `Walk<forward><normal>` → `Walk<forward><slow>` → `Turn<right><75>` → `Walk<forward><normal>` → `Walk<forward><slow>` → `Turn<right><25>` → `Walk<forward><slow>` ×2 → `Turn<right><90>` → `Turn<right><70>` → `Turn<right><25>` → `Sit down<0.45>` → `Sit down<0.40>` → `Sit down<0.38>` → `Stop/Stand`

</details>

Codex source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-codex-copilot-gemini-argon-fullval-r2-20261018/results/shard-0743/106366410_174226806_ep29_toilet/rollout_00/experiment_runs/run_ff824a6d4bc542e8a7dee62f864da56e/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

**Pi, divergence decision 1**: `Turn<right><120>`. Visible-state claim: “Facing a kitchen countertop with knife blocks and spice jars. The toilet is not visible, and the counter blocks the forward path.”

**Pi, final decision 100**: `Stop/Stand`. Visible-state claim: “Facing down the hallway, right next to the bathroom doorway on the right. The toilet is not visible, and the hallway ahead is clear.”

<details><summary>Pi complete action chain (consecutive repeats compressed)</summary>

`Turn<right><120>` ×2 → `Turn<right><35>` → `Walk<forward><fast>` ×4 → `Turn<left><80>` → `Walk<forward><fast>` → `Turn<right><25>` → `Walk<forward><fast>` → `Turn<right><25>` → `Walk<forward><fast>` → `Side step<right><0.40>` → `Walk<forward><fast>` ×3 → `Turn<left><80>` → `Turn<left><30>` → `Walk<forward><fast>` ×10 → `Turn<left><80>` → `Side step<right><0.50>` → `Side step<right><0.30>` → `Turn<left><90>` → `Turn<left><30>` → `Side step<right><0.30>` → `Walk<forward><fast>` ×4 → `Side step<right><0.40>` → `Turn<left><120>` → `Turn<left><60>` → `Walk<forward><fast>` ×2 → `Turn<left><90>` → `Side step<right><0.50>` → `Turn<left><90>` → `Walk<forward><fast>` → `Turn<right><20>` → `Turn<left><30>` → `Turn<left><20>` → `Walk<forward><fast>` ×2 → `Turn<left><120>` → `Turn<left><60>` → `Walk<forward><fast>` ×5 → `Walk<forward><normal>` → `Turn<left><80>` → `Turn<right><120>` → `Turn<right><90>` → `Turn<right><100>` → `Turn<left><25>` → `Walk<forward><fast>` → `Turn<left><85>` → `Turn<right><90>` → `Walk<forward><fast>` → `Turn<right><90>` → `Side step<left><0.50>` ×3 → `Turn<right><90>` → `Walk<forward><fast>` ×3 → `Side step<right><0.30>` → `Turn<right><25>` → `Walk<forward><fast>` → `Walk<forward><normal>` → `Turn<right><80>` → `Turn<right><100>` → `Turn<left><90>` → `Side step<right><0.50>` ×5 → `Turn<left><90>` → `Turn<right><15>` → `Walk<forward><fast>` ×2 → `Side step<left><0.50>` → `Turn<right><20>` → `Walk<forward><fast>` → `Turn<left><110>` → `Turn<left><80>` → `Stop/Stand`

</details>

Pi source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-pi-copilot-gemini-argon-fullval-r2-20261018/results/shard-0743/106366410_174226806_ep29_toilet/rollout_00/experiment_runs/run_e4bb688f9fe0401ea76a4ba500023fec/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

Saved-image review sheet: [four recorded views](../assets/C062_sheet.jpg). These are existing observations, not a replay.

Interpretation boundary: distance/contact results are evaluator facts. The quoted visible-state descriptions are model claims. Images, orientation, contact progression, and recovery behavior must be read together before assigning a causal failure label.

---

## C063: gemini / codex only

Task: scene `102816036`, episode `8`, target **chair**. Shard `shard-0128`.

Exact common action prefix: **0** decisions. The next action is the first behavioral divergence; it is not automatically the cause of the outcome.

| Harness | Terminal fact | Actions | Requests | Sit calls | Final distance (m) | Active stop | Target ever visible (GT) | Collision-step fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Codex | Success | 29 | 30 | 0 | 0.001 | True | True | 0.357 |
| Pi | Stopped outside threshold | 17 | 19 | 0 | 5.275 | True | True | 0.000 |


**Codex, divergence decision 1**: `Turn<left><60>`. Visible-state claim: “Close to a dark partition/pillar and wooden bench/coat rack area. The target chair is not clearly visible; near-body lane forward is blocked by the partition and wooden bench.”

**Codex, final decision 29**: `Stop/Stand`. Visible-state claim: “Standing directly against the backrest of the wooden dining chair with the body touching the chair at zero distance.”

<details><summary>Codex complete action chain (consecutive repeats compressed)</summary>

`Turn<left><60>` → `Turn<right><90>` → `Turn<right><120>` → `Turn<right><90>` → `Turn<right><70>` → `Walk<forward><fast>` → `Turn<right><20>` → `Walk<forward><fast>` → `Side step<right><0.30>` → `Turn<left><15>` → `Walk<forward><fast>` ×9 → `Side step<right><0.30>` → `Walk<forward><fast>` → `Side step<right><0.40>` → `Walk<forward><fast>` → `Side step<right><0.40>` → `Walk<forward><fast>` → `Turn<right><25>` → `Walk<forward><fast>` → `Walk<forward><normal>` → `Stop/Stand`

</details>

Codex source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-codex-copilot-gemini-argon-fullval-r2-20261018/results/shard-0128/102816036_ep8_chair/rollout_00/experiment_runs/run_7a320830226547b19033d541b9aa37a7/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

**Pi, divergence decision 1**: `Turn<left><90>`. Visible-state claim: “Facing a partition wall and cubbies on the left, with a wooden bench/shelf in front. No chair is clearly visible. Near-body lane forward is blocked by the partition.”

**Pi, final decision 17**: `Stop/Stand`. Visible-state claim: “The body is directly touching the round wooden chair/stool in front of the wooden desk, with zero distance to the target object.”

<details><summary>Pi complete action chain (consecutive repeats compressed)</summary>

`Turn<left><90>` ×2 → `Turn<left><45>` ×2 → `Turn<right><120>` → `Turn<left><45>` → `Turn<left><30>` → `Walk<forward><fast>` → `Walk<forward><slow>` → `Turn<right><120>` → `Turn<right><90>` → `Turn<left><120>` → `Turn<left><90>` → `Walk<forward><normal>` → `Side step<right><0.15>` → `Side step<right><0.10>` → `Stop/Stand`

</details>

Pi source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-pi-copilot-gemini-argon-fullval-r2-20261018/results/shard-0128/102816036_ep8_chair/rollout_00/experiment_runs/run_078a5e84262c46c6ae7953c8e0294dcc/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

Interpretation boundary: distance/contact results are evaluator facts. The quoted visible-state descriptions are model claims. Images, orientation, contact progression, and recovery behavior must be read together before assigning a causal failure label.

---

## C064: gemini / codex only

Task: scene `108736800_177263517`, episode `22`, target **toilet**. Shard `shard-1180`.

Exact common action prefix: **1** decisions. The next action is the first behavioral divergence; it is not automatically the cause of the outcome.

| Harness | Terminal fact | Actions | Requests | Sit calls | Final distance (m) | Active stop | Target ever visible (GT) | Collision-step fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Codex | Success | 42 | 43 | 3 | 0.000 | True | True | 0.537 |
| Pi | No valid sitting contact recorded | 41 | 42 | 2 | 0.058 | True | True | 0.575 |


**Codex, divergence decision 2**: `Turn<left><120>`. Visible-state claim: “Sofa on the left, barstools on the right, and clear floor ahead toward closet doors and dining area. The toilet is not visible.”

**Codex, final decision 42**: `Stop/Stand`. Visible-state claim: “Fully seated on the toilet with bent legs visible in the foreground, bathtub and hamper on the left, and checkered bathroom floor ahead.”

<details><summary>Codex complete action chain (consecutive repeats compressed)</summary>

`Walk<forward><fast>` → `Turn<left><120>` → `Turn<left><20>` → `Walk<forward><fast>` ×2 → `Turn<right><70>` → `Walk<forward><fast>` ×4 → `Side step<right><0.30>` ×2 → `Walk<forward><fast>` → `Turn<right><25>` → `Walk<forward><fast>` → `Side step<right><0.25>` → `Walk<forward><fast>` → `Side step<right><0.30>` → `Side step<right><0.25>` → `Turn<right><25>` → `Side step<right><0.30>` → `Walk<forward><fast>` → `Side step<right><0.30>` → `Walk<forward><fast>` → `Side step<right><0.30>` ×3 → `Walk<forward><fast>` → `Side step<right><0.30>` → `Walk<forward><fast>` → `Turn<right><20>` → `Walk<forward><fast>` ×2 → `Walk<forward><normal>` ×2 → `Turn<right><90>` → `Step back<0.30>` ×2 → `Sit down<0.45>` ×3 → `Stop/Stand`

</details>

Codex source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-codex-copilot-gemini-argon-fullval-r2-20261018/results/shard-1180/108736800_177263517_ep22_toilet/rollout_00/experiment_runs/run_e165baa8ac514c92aadfdf6f76db8352/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

**Pi, divergence decision 2**: `Turn<right><90>`. Visible-state claim: “Walking along the corridor between the sofa on the left and bar stools on the right. The toilet is not visible. Near-body lane ahead is clear.”

**Pi, final decision 41**: `Stop/Stand`. Visible-state claim: “Fully seated on the toilet with zero distance to the target object. Submitting final pose.”

<details><summary>Pi complete action chain (consecutive repeats compressed)</summary>

`Walk<forward><fast>` → `Turn<right><90>` ×3 → `Turn<left><45>` → `Walk<forward><fast>` ×3 → `Turn<right><70>` → `Walk<forward><fast>` ×5 → `Turn<right><35>` → `Turn<left><45>` → `Side step<left><0.25>` → `Turn<right><25>` → `Walk<forward><fast>` → `Side step<right><0.15>` ×2 → `Turn<right><20>` → `Walk<forward><fast>` → `Side step<right><0.25>` → `Side step<right><0.20>` → `Walk<forward><fast>` ×2 → `Side step<right><0.15>` ×2 → `Walk<forward><fast>` → `Side step<right><0.25>` → `Walk<forward><fast>` ×3 → `Walk<forward><normal>` → `Walk<forward><slow>` → `Turn<right><90>` → `Turn<right><25>` → `Sit down<0.45>` ×2 → `Stop/Stand`

</details>

Pi source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-pi-copilot-gemini-argon-fullval-r2-20261018/results/shard-1180/108736800_177263517_ep22_toilet/rollout_00/experiment_runs/run_2047e44870d54e76a77b4d394e6fd028/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

Interpretation boundary: distance/contact results are evaluator facts. The quoted visible-state descriptions are model claims. Images, orientation, contact progression, and recovery behavior must be read together before assigning a causal failure label.

---

## C065: gemini / codex only

Task: scene `104862384_172226319`, episode `21`, target **tv**. Shard `shard-0497`.

Exact common action prefix: **2** decisions. The next action is the first behavioral divergence; it is not automatically the cause of the outcome.

| Harness | Terminal fact | Actions | Requests | Sit calls | Final distance (m) | Active stop | Target ever visible (GT) | Collision-step fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Codex | Success | 16 | 17 | 0 | 0.198 | True | True | 0.200 |
| Pi | Stopped outside threshold | 16 | 17 | 0 | 0.309 | True | True | 0.067 |


**Codex, divergence decision 3**: `Turn<left><45>`. Visible-state claim: “Looking from the entryway into a living room with a rug, coffee table, white sofa edge, armchair, and a wooden console on the left. A small stool is slightly ahead to the right. The TV is not yet visible. The lane to the left of the stool is open.”

**Codex, final decision 16**: `Stop/Stand`. Visible-state claim: “The black TV is directly in front and the body is touching the TV stand right at the TV with zero distance remaining. The forward lane is blocked by the target.”

<details><summary>Codex complete action chain (consecutive repeats compressed)</summary>

`Turn<left><90>` ×2 → `Turn<left><45>` → `Walk<forward><fast>` → `Turn<right><25>` → `Walk<forward><fast>` → `Side step<right><0.40>` ×3 → `Walk<forward><fast>` → `Walk<forward><normal>` → `Turn<left><80>` → `Walk<forward><slow>` → `Side step<right><0.20>` → `Walk<forward><slow>` → `Stop/Stand`

</details>

Codex source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-codex-copilot-gemini-argon-fullval-r2-20261018/results/shard-0497/104862384_172226319_ep21_tv/rollout_00/experiment_runs/run_245786a052ee483d91e5bf2703a6c515/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

**Pi, divergence decision 3**: `Turn<left><30>`. Visible-state claim: “Looking from the entryway into a living/dining room. A small stool is slightly to the right, and a clear path leads forward-left into the room. The TV is not yet visible. Near-body lane to the left-forward is clear.”

**Pi, final decision 16**: `Stop/Stand`. Visible-state claim: “The TV is directly in front of the body at point-blank range, and the body is pressed directly against the TV cabinet/TV with no further forward movement possible.”

<details><summary>Pi complete action chain (consecutive repeats compressed)</summary>

`Turn<left><90>` ×2 → `Turn<left><30>` → `Walk<forward><fast>` ×2 → `Turn<right><15>` → `Side step<right><0.30>` ×3 → `Walk<forward><fast>` ×2 → `Turn<left><90>` → `Walk<forward><slow>` ×3 → `Stop/Stand`

</details>

Pi source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-pi-copilot-gemini-argon-fullval-r2-20261018/results/shard-0497/104862384_172226319_ep21_tv/rollout_00/experiment_runs/run_33657f8a28c94a67bc0f959dad9f2198/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

Interpretation boundary: distance/contact results are evaluator facts. The quoted visible-state descriptions are model claims. Images, orientation, contact progression, and recovery behavior must be read together before assigning a causal failure label.

---

## C066: gemini / pi only

Task: scene `102816600`, episode `1`, target **potted_plant**. Shard `shard-0179`.

Exact common action prefix: **0** decisions. The next action is the first behavioral divergence; it is not automatically the cause of the outcome.

| Harness | Terminal fact | Actions | Requests | Sit calls | Final distance (m) | Active stop | Target ever visible (GT) | Collision-step fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Codex | Stopped outside threshold | 21 | 22 | 0 | 1.304 | True | False | 0.050 |
| Pi | Success | 46 | 52 | 0 | 0.000 | True | True | 0.489 |


**Codex, divergence decision 1**: `Turn<right><90>`. Visible-state claim: “Facing a grassy area on the left and a blue car on a driveway on the right, with black void ahead. The potted plant target is not visible. The near-body lane is clear.”

**Codex, final decision 21**: `Stop/Stand`. Visible-state claim: “Body is directly touching the white potted plant box with zero distance; the near-body lane ahead is occupied by the target.”

<details><summary>Codex complete action chain (consecutive repeats compressed)</summary>

`Turn<right><90>` ×2 → `Turn<left><80>` → `Turn<left><20>` → `Walk<forward><fast>` ×4 → `Side step<right><0.35>` → `Side step<right><0.30>` → `Walk<forward><fast>` ×4 → `Turn<right><25>` → `Walk<forward><fast>` → `Walk<forward><normal>` ×2 → `Side step<right><0.20>` → `Walk<forward><slow>` → `Stop/Stand`

</details>

Codex source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-codex-copilot-gemini-argon-fullval-r2-20261018/results/shard-0179/102816600_ep1_potted_plant/rollout_00/experiment_runs/run_c16c8f97af994f6a9403570783b6b189/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

**Pi, divergence decision 1**: `Turn<left><90>`. Visible-state claim: “Facing a grass lawn and the edge of the scene, with a blue SUV parked on a driveway to the right. The potted plant target is not visible. The near-body lane ahead is clear grass.”

**Pi, final decision 46**: `Stop/Stand`. Visible-state claim: “The cyan body is directly touching the black pot and foliage of the target potted plant at zero distance. The near-body lane is occupied by the potted plant and wall.”

<details><summary>Pi complete action chain (consecutive repeats compressed)</summary>

`Turn<left><90>` → `Turn<left><60>` ×3 → `Walk<forward><fast>` ×2 → `Turn<right><70>` → `Turn<left><90>` → `Turn<right><120>` → `Turn<right><90>` → `Walk<forward><fast>` ×12 → `Turn<right><20>` → `Walk<forward><fast>` ×6 → `Turn<right><20>` → `Walk<forward><fast>` ×3 → `Turn<left><90>` → `Walk<forward><fast>` → `Walk<forward><normal>` → `Turn<left><60>` → `Turn<left><30>` → `Walk<forward><fast>` → `Turn<right><50>` → `Walk<forward><normal>` → `Turn<right><15>` → `Turn<right><25>` → `Walk<forward><slow>` → `Side step<right><0.15>` → `Stop/Stand`

</details>

Pi source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-pi-copilot-gemini-argon-fullval-r2-20261018/results/shard-0179/102816600_ep1_potted_plant/rollout_00/experiment_runs/run_13e540df4f624041925f6d8c4580a4b4/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

Saved-image review sheet: [four recorded views](../assets/C066_sheet.jpg). These are existing observations, not a replay.

Interpretation boundary: distance/contact results are evaluator facts. The quoted visible-state descriptions are model claims. Images, orientation, contact progression, and recovery behavior must be read together before assigning a causal failure label.

---

## C067: gemini / pi only

Task: scene `102816756`, episode `17`, target **bed**. Shard `shard-0225`.

Exact common action prefix: **3** decisions. The next action is the first behavioral divergence; it is not automatically the cause of the outcome.

| Harness | Terminal fact | Actions | Requests | Sit calls | Final distance (m) | Active stop | Target ever visible (GT) | Collision-step fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Codex | No valid sitting contact recorded | 32 | 35 | 2 | 0.000 | True | True | 0.484 |
| Pi | Success | 30 | 33 | 2 | 0.000 | True | True | 0.448 |


**Codex, divergence decision 4**: `Turn<left><90>`. Visible-state claim: “Looking at the dark armchairs on the left and open wooden floor ahead. The bed is not visible. Near-body lane ahead is clear.”

**Codex, final decision 32**: `Stop/Stand`. Visible-state claim: “Seated directly on the corner of the bed with the bed visible beneath and beside the body. Near-body lane ahead is clear.”

<details><summary>Codex complete action chain (consecutive repeats compressed)</summary>

`Turn<right><90>` ×2 → `Turn<left><120>` → `Turn<left><90>` → `Walk<forward><fast>` ×2 → `Turn<right><25>` → `Walk<forward><fast>` → `Turn<right><20>` → `Side step<right><0.30>` ×2 → `Walk<forward><fast>` → `Side step<right><0.30>` → `Walk<forward><fast>` ×3 → `Side step<right><0.30>` → `Walk<forward><fast>` → `Turn<left><30>` → `Turn<left><15>` → `Walk<forward><fast>` ×3 → `Turn<right><35>` → `Walk<forward><fast>` ×2 → `Walk<forward><normal>` → `Turn<left><120>` → `Turn<left><90>` → `Sit down<0.50>` → `Sit down<0.45>` → `Stop/Stand`

</details>

Codex source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-codex-copilot-gemini-argon-fullval-r2-20261018/results/shard-0225/102816756_ep17_bed/rollout_00/experiment_runs/run_48401b29527341558eb15c7bde99b9ec/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

**Pi, divergence decision 4**: `Turn<left><80>`. Visible-state claim: “Facing the living/dining room with dark armchairs on the left. The bed is not visible; near-body lane is clear.”

**Pi, final decision 30**: `Stop/Stand`. Visible-state claim: “Seated directly on the edge of the bed with zero distance to the bed. Submitting final pose.”

<details><summary>Pi complete action chain (consecutive repeats compressed)</summary>

`Turn<right><90>` ×2 → `Turn<left><120>` → `Turn<left><80>` → `Walk<forward><fast>` ×2 → `Turn<right><25>` → `Walk<forward><fast>` ×2 → `Side step<right><0.30>` → `Walk<forward><fast>` → `Side step<right><0.30>` → `Walk<forward><fast>` ×3 → `Side step<right><0.40>` → `Walk<forward><fast>` → `Turn<left><30>` → `Walk<forward><fast>` ×3 → `Turn<right><25>` → `Walk<forward><fast>` → `Walk<forward><normal>` ×2 → `Turn<left><120>` → `Step back<0.20>` → `Sit down<0.45>` ×2 → `Stop/Stand`

</details>

Pi source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-pi-copilot-gemini-argon-fullval-r2-20261018/results/shard-0225/102816756_ep17_bed/rollout_00/experiment_runs/run_a5f6caee4eac46dab253778f332bc931/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

Saved-image review sheet: [four recorded views](../assets/C067_sheet.jpg). These are existing observations, not a replay.

Interpretation boundary: distance/contact results are evaluator facts. The quoted visible-state descriptions are model claims. Images, orientation, contact progression, and recovery behavior must be read together before assigning a causal failure label.

---

## C068: gemini / pi only

Task: scene `102816036`, episode `15`, target **potted_plant**. Shard `shard-0135`.

Exact common action prefix: **1** decisions. The next action is the first behavioral divergence; it is not automatically the cause of the outcome.

| Harness | Terminal fact | Actions | Requests | Sit calls | Final distance (m) | Active stop | Target ever visible (GT) | Collision-step fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Codex | Stopped outside threshold | 100 | 108 | 0 | 0.519 | True | True | 0.182 |
| Pi | Success | 63 | 70 | 0 | 0.000 | True | True | 0.177 |


**Codex, divergence decision 2**: `Walk<forward><fast>`. Visible-state claim: “Looking along the bathroom counter with a white flower pot on the left, a toilet room ahead, and an open doorway to a dining/living area on the right. The near-body lane ahead is clear.”

**Codex, final decision 100**: `Stop/Stand`. Visible-state claim: “Standing beside the wooden cabinet and wall painting in the dining room. Stopping on final action.”

<details><summary>Codex complete action chain (consecutive repeats compressed)</summary>

`Turn<right><60>` → `Walk<forward><fast>` ×2 → `Turn<right><60>` → `Walk<forward><fast>` ×2 → `Turn<left><30>` → `Walk<forward><fast>` ×3 → `Turn<left><60>` → `Walk<forward><fast>` → `Turn<left><60>` → `Walk<forward><fast>` ×3 → `Side step<right><0.40>` ×2 → `Turn<right><20>` → `Walk<forward><fast>` ×7 → `Turn<left><60>` → `Turn<right><60>` → `Turn<right><30>` ×2 → `Side step<right><0.40>` ×2 → `Walk<forward><fast>` ×2 → `Turn<left><30>` → `Walk<forward><fast>` ×4 → `Turn<left><90>` → `Turn<right><120>` → `Turn<right><60>` → `Walk<forward><fast>` → `Turn<right><60>` → `Turn<left><120>` ×2 → `Walk<forward><fast>` → `Turn<right><60>` → `Turn<left><40>` → `Turn<right><50>` → `Walk<forward><fast>` ×2 → `Turn<left><120>` → `Turn<left><60>` → `Walk<forward><fast>` ×2 → `Turn<right><70>` → `Turn<left><70>` → `Walk<forward><fast>` → `Turn<right><20>` → `Walk<forward><fast>` → `Turn<left><15>` → `Side step<left><0.30>` → `Walk<forward><fast>` ×4 → `Turn<right><70>` → `Turn<right><50>` → `Walk<forward><fast>` ×2 → `Side step<left><0.30>` → `Walk<forward><fast>` ×4 → `Turn<right><30>` → `Walk<forward><fast>` → `Side step<right><0.25>` → `Walk<forward><fast>` → `Turn<right><90>` → `Walk<forward><fast>` → `Turn<left><30>` → `Walk<forward><fast>` → `Side step<left><0.40>` ×3 → `Turn<left><30>` → `Walk<forward><fast>` → `Turn<right><50>` → `Side step<right><0.30>` → `Side step<right><0.25>` → `Walk<forward><fast>` ×2 → `Turn<right><50>` → `Walk<forward><fast>` → `Turn<left><80>` → `Turn<right><70>` → `Walk<forward><normal>` → `Stop/Stand`

</details>

Codex source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-codex-copilot-gemini-argon-fullval-r2-20261018/results/shard-0135/102816036_ep15_potted_plant/rollout_00/experiment_runs/run_91ef082793914f97b008f6d080cd21c0/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

**Pi, divergence decision 2**: `Turn<right><90>`. Visible-state claim: “Looking towards the toilet doorway and another doorway leading to a living/dining area. Near-body lane is clear. Turning right to inspect the rest of this room first.”

**Pi, final decision 63**: `Stop/Stand`. Visible-state claim: “Body is directly touching the target potted plant with zero distance. Near-body lane ahead is occupied by the target potted plant. Stopping and standing to finish the task.”

<details><summary>Pi complete action chain (consecutive repeats compressed)</summary>

`Turn<right><60>` → `Turn<right><90>` ×2 → `Turn<left><120>` → `Turn<left><60>` → `Walk<forward><fast>` → `Walk<forward><normal>` → `Walk<forward><fast>` → `Turn<left><60>` → `Turn<right><90>` → `Side step<right><0.40>` ×2 → `Turn<left><25>` → `Walk<forward><fast>` ×5 → `Side step<right><0.30>` → `Walk<forward><fast>` → `Turn<left><60>` → `Turn<right><90>` → `Turn<right><60>` → `Turn<left><80>` → `Turn<left><60>` → `Walk<forward><fast>` ×3 → `Turn<left><35>` → `Walk<forward><fast>` ×6 → `Turn<left><80>` → `Turn<right><80>` → `Turn<right><25>` → `Walk<forward><fast>` ×7 → `Turn<right><70>` → `Turn<left><70>` → `Walk<forward><fast>` → `Turn<left><60>` → `Turn<right><70>` → `Walk<forward><fast>` → `Side step<right><0.30>` → `Walk<forward><fast>` → `Turn<right><25>` → `Walk<forward><fast>` → `Turn<right><25>` → `Side step<right><0.40>` → `Turn<right><50>` → `Turn<right><25>` → `Walk<forward><normal>` → `Walk<forward><slow>` ×2 → `Stop/Stand`

</details>

Pi source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-pi-copilot-gemini-argon-fullval-r2-20261018/results/shard-0135/102816036_ep15_potted_plant/rollout_00/experiment_runs/run_207422a0da374d969fd9cb5b83289239/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

Interpretation boundary: distance/contact results are evaluator facts. The quoted visible-state descriptions are model claims. Images, orientation, contact progression, and recovery behavior must be read together before assigning a causal failure label.

---

## C069: gemini / pi only

Task: scene `102344094`, episode `0`, target **couch**. Shard `shard-0030`.

Exact common action prefix: **2** decisions. The next action is the first behavioral divergence; it is not automatically the cause of the outcome.

| Harness | Terminal fact | Actions | Requests | Sit calls | Final distance (m) | Active stop | Target ever visible (GT) | Collision-step fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Codex | No valid sitting contact recorded | 15 | 17 | 2 | 0.037 | True | True | 0.500 |
| Pi | Success | 18 | 20 | 2 | 0.003 | True | True | 0.412 |


**Codex, divergence decision 3**: `Turn<right><35>`. Visible-state claim: “The couch is visible in the living room area ahead-left past the kitchen counter. Near-body lane straight ahead is partially blocked by the kitchen counter on the left, while the walkway on the right is clear.”

**Codex, final decision 15**: `Stop/Stand`. Visible-state claim: “Seated on the couch with the edge of the couch visible under the right leg and the red rug and wood floor ahead. Near-body lane ahead is clear.”

<details><summary>Codex complete action chain (consecutive repeats compressed)</summary>

`Turn<right><90>` → `Turn<right><120>` → `Turn<right><35>` → `Walk<forward><fast>` ×2 → `Turn<left><90>` → `Walk<forward><fast>` ×5 → `Turn<left><80>` → `Sit down<0.45>` ×2 → `Stop/Stand`

</details>

Codex source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-codex-copilot-gemini-argon-fullval-r2-20261018/results/shard-0030/102344094_ep0_couch/rollout_00/experiment_runs/run_5d48abbfaa5a40d3881f1b61d3bb2bdf/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

**Pi, divergence decision 3**: `Turn<right><25>`. Visible-state claim: “The beige sectional couch is visible in the living room ahead-left. Immediately in front-left is the kitchen counter corner. Turning slightly right to align with the clear walkway out of the kitchen.”

**Pi, final decision 18**: `Stop/Stand`. Visible-state claim: “Fully seated on the couch cushion with legs bent and the couch armrest next to the right arm. Submitting final pose.”

<details><summary>Pi complete action chain (consecutive repeats compressed)</summary>

`Turn<right><90>` → `Turn<right><120>` → `Turn<right><25>` → `Walk<forward><fast>` ×2 → `Walk<forward><normal>` → `Turn<left><60>` → `Walk<forward><fast>` → `Turn<left><25>` → `Walk<forward><fast>` ×2 → `Walk<forward><slow>` → `Side step<right><0.20>` → `Turn<left><90>` ×2 → `Sit down<0.45>` ×2 → `Stop/Stand`

</details>

Pi source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-pi-copilot-gemini-argon-fullval-r2-20261018/results/shard-0030/102344094_ep0_couch/rollout_00/experiment_runs/run_28ff786596294ae79068877e35f0d072/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

Interpretation boundary: distance/contact results are evaluator facts. The quoted visible-state descriptions are model claims. Images, orientation, contact progression, and recovery behavior must be read together before assigning a causal failure label.

---

## C070: gemini / pi only

Task: scene `108736779_177263484`, episode `10`, target **potted_plant**. Shard `shard-1140`.

Exact common action prefix: **7** decisions. The next action is the first behavioral divergence; it is not automatically the cause of the outcome.

| Harness | Terminal fact | Actions | Requests | Sit calls | Final distance (m) | Active stop | Target ever visible (GT) | Collision-step fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Codex | Stopped outside threshold | 21 | 22 | 0 | 0.256 | True | True | 0.250 |
| Pi | Success | 71 | 76 | 0 | 0.000 | True | True | 0.386 |


**Codex, divergence decision 8**: `Walk<forward><fast>`. Visible-state claim: “Moving closer to the kitchen doorway on the right and the second doorway further ahead. The potted plant is not visible yet. The near-body lane is clear.”

**Codex, final decision 21**: `Stop/Stand`. Visible-state claim: “Standing directly against the round dining table with the potted plant centered right in front of the body. The target potted plant is clearly visible and as close as possible, with the near-body lane occupied by the table holding the plant.”

<details><summary>Codex complete action chain (consecutive repeats compressed)</summary>

`Turn<right><90>` ×3 → `Turn<left><30>` ×2 → `Walk<forward><fast>` ×3 → `Turn<right><35>` → `Walk<forward><fast>` ×4 → `Turn<left><45>` → `Turn<right><70>` → `Side step<right><0.40>` → `Walk<forward><normal>` → `Turn<right><25>` → `Walk<forward><slow>` → `Side step<right><0.20>` → `Stop/Stand`

</details>

Codex source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-codex-copilot-gemini-argon-fullval-r2-20261018/results/shard-1140/108736779_177263484_ep10_potted_plant/rollout_00/experiment_runs/run_0d0a2b9e614149c7843ce6e3297ca3d9/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

**Pi, divergence decision 8**: `Turn<right><35>`. Visible-state claim: “Current view shows the kitchen doorway ahead-right with cabinets, fridge, and chairs visible inside. The potted plant is not visible. Near-body lane is clear.”

**Pi, final decision 71**: `Stop/Stand`. Visible-state claim: “Current view shows the potted plant directly touching the agent's body at zero distance. Near-body lane is in contact with the target potted plant.”

<details><summary>Pi complete action chain (consecutive repeats compressed)</summary>

`Turn<right><90>` ×3 → `Turn<left><30>` ×2 → `Walk<forward><fast>` ×2 → `Turn<right><35>` → `Walk<forward><fast>` ×4 → `Turn<right><35>` → `Walk<forward><fast>` → `Turn<right><35>` → `Turn<right><70>` → `Turn<right><90>` → `Walk<forward><fast>` ×3 → `Turn<left><25>` → `Walk<forward><fast>` → `Turn<right><70>` ×2 → `Turn<left><25>` → `Walk<forward><fast>` ×3 → `Turn<right><50>` → `Walk<forward><fast>` ×2 → `Turn<right><70>` → `Turn<left><90>` → `Turn<left><60>` → `Walk<forward><fast>` ×3 → `Turn<right><25>` → `Walk<forward><fast>` → `Turn<left><25>` → `Turn<left><45>` → `Turn<right><40>` → `Walk<forward><fast>` → `Turn<right><35>` ×2 → `Walk<forward><fast>` → `Turn<right><20>` → `Walk<forward><fast>` ×3 → `Turn<left><80>` → `Turn<left><60>` → `Turn<right><120>` → `Turn<right><70>` → `Turn<right><90>` → `Walk<forward><fast>` → `Turn<right><25>` → `Walk<forward><fast>` → `Turn<right><50>` → `Turn<right><25>` → `Turn<left><15>` → `Walk<forward><fast>` ×3 → `Turn<right><60>` → `Turn<right><50>` → `Walk<forward><fast>` → `Turn<right><25>` → `Walk<forward><slow>` ×2 → `Stop/Stand`

</details>

Pi source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-pi-copilot-gemini-argon-fullval-r2-20261018/results/shard-1140/108736779_177263484_ep10_potted_plant/rollout_00/experiment_runs/run_520bf346b5294cc69424583b74c8ea02/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

Interpretation boundary: distance/contact results are evaluator facts. The quoted visible-state descriptions are model claims. Images, orientation, contact progression, and recovery behavior must be read together before assigning a causal failure label.

---

## C071: gemini / both success

Task: scene `108736800_177263517`, episode `11`, target **tv**. Shard `shard-1169`.

Exact common action prefix: **3** decisions. The next action is the first behavioral divergence; it is not automatically the cause of the outcome.

| Harness | Terminal fact | Actions | Requests | Sit calls | Final distance (m) | Active stop | Target ever visible (GT) | Collision-step fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Codex | Success | 42 | 43 | 0 | 0.044 | True | True | 0.561 |
| Pi | Success | 29 | 32 | 0 | 0.048 | True | True | 0.679 |


**Codex, divergence decision 4**: `Turn<right><120>`. Visible-state claim: “Facing a doorway wall with a desk/cabinet visible on the left; the TV target is not visible, and the wall blocks the right/center.”

**Codex, final decision 42**: `Stop/Stand`. Visible-state claim: “Standing in contact with the fireplace wall directly against the wall-mounted TV; the TV target fills the upper view and the near-body lane ahead is blocked by the TV and wall.”

<details><summary>Codex complete action chain (consecutive repeats compressed)</summary>

`Turn<right><90>` ×3 → `Turn<right><120>` → `Turn<right><30>` → `Walk<forward><fast>` ×6 → `Walk<forward><normal>` → `Turn<left><90>` → `Side step<right><0.30>` ×2 → `Walk<forward><fast>` ×2 → `Turn<left><90>` → `Turn<right><90>` → `Side step<right><0.50>` ×2 → `Walk<forward><fast>` ×2 → `Turn<left><120>` → `Side step<right><0.50>` ×2 → `Walk<forward><fast>` ×2 → `Side step<right><0.30>` → `Walk<forward><fast>` → `Side step<right><0.20>` → `Walk<forward><fast>` ×2 → `Turn<left><90>` → `Side step<right><0.40>` ×2 → `Side step<right><0.30>` → `Turn<right><25>` → `Walk<forward><normal>` ×2 → `Walk<forward><slow>` → `Stop/Stand`

</details>

Codex source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-codex-copilot-gemini-argon-fullval-r2-20261018/results/shard-1169/108736800_177263517_ep11_tv/rollout_00/experiment_runs/run_8b87bef57c2149fba1a3f6ad6fabc938/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

**Pi, divergence decision 4**: `Turn<left><60>`. Visible-state claim: “Facing a dark wall and doorframe on the right, with a desk and plant visible on the left. The TV is not visible. Near-body lane straight ahead is blocked by the wall/doorframe.”

**Pi, final decision 29**: `Stop/Stand`. Visible-state claim: “Directly facing and touching the wall-mounted TV and its wall with zero distance. Near-body lane ahead is completely occupied by the target TV/wall.”

<details><summary>Pi complete action chain (consecutive repeats compressed)</summary>

`Turn<right><90>` ×3 → `Turn<left><60>` → `Turn<left><120>` → `Turn<left><60>` → `Walk<forward><fast>` ×5 → `Side step<right><0.30>` → `Walk<forward><fast>` → `Side step<right><0.40>` → `Walk<forward><fast>` → `Turn<left><90>` → `Turn<left><45>` → `Turn<right><60>` → `Walk<forward><fast>` → `Turn<left><90>` → `Side step<right><0.50>` → `Turn<right><25>` → `Walk<forward><fast>` ×2 → `Walk<forward><normal>` → `Turn<left><90>` → `Walk<forward><slow>` ×2 → `Stop/Stand`

</details>

Pi source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-pi-copilot-gemini-argon-fullval-r2-20261018/results/shard-1169/108736800_177263517_ep11_tv/rollout_00/experiment_runs/run_b8bc01e159e9433080365fa4d9eaabac/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

Saved-image review sheet: [four recorded views](../assets/C071_sheet.jpg). These are existing observations, not a replay.

Interpretation boundary: distance/contact results are evaluator facts. The quoted visible-state descriptions are model claims. Images, orientation, contact progression, and recovery behavior must be read together before assigning a causal failure label.

---

## C072: gemini / both success

Task: scene `104348361_171513414`, episode `28`, target **bed**. Shard `shard-0474`.

Exact common action prefix: **2** decisions. The next action is the first behavioral divergence; it is not automatically the cause of the outcome.

| Harness | Terminal fact | Actions | Requests | Sit calls | Final distance (m) | Active stop | Target ever visible (GT) | Collision-step fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Codex | Success | 34 | 36 | 4 | 0.054 | True | True | 0.576 |
| Pi | Success | 25 | 32 | 2 | 0.091 | True | True | 0.458 |


**Codex, divergence decision 3**: `Walk<forward><fast>`. Visible-state claim: “Looking down a wooden hallway with doorways on the left; through the nearer doorway on the left a corner of a bed or sofa frame is partially visible. The near-body lane ahead is clear.”

**Codex, final decision 34**: `Stop/Stand`. Visible-state claim: “Fully seated on the side of the bed next to the nightstand with legs in front. The near-body lane ahead is clear.”

<details><summary>Codex complete action chain (consecutive repeats compressed)</summary>

`Turn<right><90>` ×2 → `Walk<forward><fast>` → `Turn<right><25>` → `Walk<forward><fast>` ×2 → `Side step<right><0.30>` → `Walk<forward><fast>` → `Turn<left><45>` → `Walk<forward><fast>` ×3 → `Turn<right><90>` → `Walk<forward><fast>` → `Turn<right><90>` → `Side step<left><0.40>` → `Turn<left><45>` → `Turn<left><90>` → `Walk<forward><normal>` → `Turn<right><90>` → `Step back<0.20>` → `Sit down<0.45>` ×2 → `Side step<right><0.40>` ×2 → `Turn<left><90>` ×2 → `Walk<forward><normal>` → `Turn<right><90>` → `Turn<right><60>` → `Step back<0.30>` → `Sit down<0.55>` ×2 → `Stop/Stand`

</details>

Codex source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-codex-copilot-gemini-argon-fullval-r2-20261018/results/shard-0474/104348361_171513414_ep28_bed/rollout_00/experiment_runs/run_2859aeffa9754c248d9241a2418c8eca/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

**Pi, divergence decision 3**: `Turn<left><30>`. Visible-state claim: “Looking down a hallway on the right with multiple doorways, and a doorway on the left. The bed is not clearly visible yet. The near-body lane is clear.”

**Pi, final decision 25**: `Stop/Stand`. Visible-state claim: “Seated firmly on the edge of the bed with both legs resting against the bed frame.”

<details><summary>Pi complete action chain (consecutive repeats compressed)</summary>

`Turn<right><90>` ×2 → `Turn<left><30>` → `Turn<right><50>` → `Turn<right><30>` → `Walk<forward><fast>` ×3 → `Turn<left><90>` → `Walk<forward><fast>` → `Side step<right><0.30>` → `Walk<forward><fast>` → `Side step<right><0.20>` → `Walk<forward><fast>` ×2 → `Walk<forward><normal>` → `Side step<right><0.30>` → `Walk<forward><slow>` → `Turn<right><120>` → `Walk<forward><normal>` → `Turn<right><70>` → `Step back<0.20>` → `Sit down<0.50>` ×2 → `Stop/Stand`

</details>

Pi source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-pi-copilot-gemini-argon-fullval-r2-20261018/results/shard-0474/104348361_171513414_ep28_bed/rollout_00/experiment_runs/run_8be41c57f37b4b73b576ba92973e4270/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

Interpretation boundary: distance/contact results are evaluator facts. The quoted visible-state descriptions are model claims. Images, orientation, contact progression, and recovery behavior must be read together before assigning a causal failure label.

---

## C073: gemini / both success

Task: scene `106366410_174226806`, episode `2`, target **potted_plant**. Shard `shard-0716`.

Exact common action prefix: **0** decisions. The next action is the first behavioral divergence; it is not automatically the cause of the outcome.

| Harness | Terminal fact | Actions | Requests | Sit calls | Final distance (m) | Active stop | Target ever visible (GT) | Collision-step fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Codex | Success | 35 | 36 | 0 | 0.000 | True | True | 0.412 |
| Pi | Success | 47 | 50 | 0 | 0.000 | True | True | 0.413 |


**Codex, divergence decision 1**: `Turn<left><90>`. Visible-state claim: “The image shows a wooden floor with a black mat, dumbbells against a wall, a tall wardrobe, and a desk with an office chair to the left. The potted plant is not visible. The near-body lane ahead is clear.”

**Codex, final decision 35**: `Stop/Stand`. Visible-state claim: “The image shows the potted plant directly in contact with the agent's body at the bottom of the frame. The target is visible and touching the body, and the near-body lane is occupied by the potted plant.”

<details><summary>Codex complete action chain (consecutive repeats compressed)</summary>

`Turn<left><90>` → `Turn<right><35>` → `Turn<right><40>` → `Turn<left><15>` → `Walk<forward><fast>` ×4 → `Side step<left><0.40>` → `Walk<forward><fast>` ×2 → `Turn<right><15>` → `Walk<forward><fast>` → `Side step<right><0.20>` → `Walk<forward><fast>` → `Side step<right><0.15>` → `Walk<forward><fast>` → `Side step<right><0.30>` → `Side step<right><0.25>` → `Walk<forward><fast>` → `Turn<right><25>` → `Side step<right><0.30>` ×2 → `Walk<forward><fast>` → `Turn<right><15>` → `Walk<forward><fast>` ×5 → `Turn<left><15>` → `Walk<forward><fast>` → `Walk<forward><normal>` → `Side step<left><0.15>` → `Stop/Stand`

</details>

Codex source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-codex-copilot-gemini-argon-fullval-r2-20261018/results/shard-0716/106366410_174226806_ep2_potted_plant/rollout_00/experiment_runs/run_771e956072aa4694bede9ff8c36ffc83/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

**Pi, divergence decision 1**: `Turn<left><60>`. Visible-state claim: “Facing a wall with a wardrobe, dumbbells, and yoga mat on the floor, and a desk with an office chair to the left. No potted plant is visible yet. Near-body lane is clear.”

**Pi, final decision 47**: `Stop/Stand`. Visible-state claim: “Touching the potted plant with zero distance, leaves and pot base in contact with the body. Stopping to complete the task.”

<details><summary>Pi complete action chain (consecutive repeats compressed)</summary>

`Turn<left><60>` → `Turn<left><80>` → `Turn<left><90>` → `Turn<right><120>` → `Turn<right><60>` → `Walk<forward><fast>` → `Turn<right><25>` → `Walk<forward><fast>` ×5 → `Turn<left><90>` → `Turn<right><90>` → `Turn<right><15>` → `Side step<left><0.25>` → `Turn<left><20>` → `Walk<forward><fast>` → `Side step<right><0.25>` → `Side step<right><0.15>` → `Walk<forward><fast>` ×2 → `Side step<right><0.15>` → `Walk<forward><fast>` → `Side step<right><0.35>` → `Turn<right><25>` → `Side step<right><0.15>` → `Turn<left><12>` → `Walk<forward><fast>` ×2 → `Turn<left><12>` → `Walk<forward><fast>` ×3 → `Turn<right><10>` → `Walk<forward><fast>` → `Turn<left><10>` → `Walk<forward><normal>` → `Turn<left><12>` → `Walk<forward><slow>` ×2 → `Side step<right><0.10>` → `Walk<forward><slow>` ×4 → `Stop/Stand`

</details>

Pi source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-pi-copilot-gemini-argon-fullval-r2-20261018/results/shard-0716/106366410_174226806_ep2_potted_plant/rollout_00/experiment_runs/run_030818c8a12248f9b67a1584dd874323/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

Interpretation boundary: distance/contact results are evaluator facts. The quoted visible-state descriptions are model claims. Images, orientation, contact progression, and recovery behavior must be read together before assigning a causal failure label.

---

## C074: gemini / both success

Task: scene `106878960_174887073`, episode `22`, target **bed**. Shard `shard-0856`.

Exact common action prefix: **0** decisions. The next action is the first behavioral divergence; it is not automatically the cause of the outcome.

| Harness | Terminal fact | Actions | Requests | Sit calls | Final distance (m) | Active stop | Target ever visible (GT) | Collision-step fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Codex | Success | 55 | 58 | 2 | 0.000 | True | True | 0.574 |
| Pi | Success | 61 | 71 | 3 | 0.000 | True | True | 0.767 |


**Codex, divergence decision 1**: `Turn<left><90>`. Visible-state claim: “Facing a kitchen stove and countertops. The bed is not visible. The near-body lane ahead is blocked by the stove, and a counter is on the right.”

**Codex, final decision 55**: `Stop/Stand`. Visible-state claim: “Seated firmly on the side of the bed with thighs resting on the mattress and feet on the rug in front of the vanity table. The near-body lane ahead is clear.”

<details><summary>Codex complete action chain (consecutive repeats compressed)</summary>

`Turn<left><90>` → `Turn<left><45>` → `Turn<right><25>` → `Turn<left><90>` → `Turn<right><95>` → `Turn<right><25>` → `Walk<forward><fast>` ×2 → `Turn<left><60>` → `Walk<forward><normal>` → `Turn<left><25>` → `Walk<forward><fast>` ×2 → `Turn<right><70>` → `Turn<left><70>` → `Turn<left><30>` → `Walk<forward><fast>` → `Turn<right><70>` → `Turn<right><25>` → `Walk<forward><fast>` ×2 → `Turn<right><25>` → `Turn<left><90>` → `Walk<forward><fast>` → `Turn<left><25>` → `Walk<forward><fast>` ×4 → `Turn<left><60>` → `Turn<left><30>` → `Walk<forward><fast>` ×6 → `Turn<left><25>` → `Walk<forward><fast>` → `Turn<right><15>` → `Turn<right><20>` → `Walk<forward><fast>` → `Turn<left><25>` → `Walk<forward><fast>` ×2 → `Turn<right><25>` ×2 → `Side step<right><0.40>` → `Walk<forward><normal>` → `Turn<right><90>` → `Turn<right><25>` → `Step back<0.15>` → `Sit down<0.50>` → `Sit down<0.45>` → `Stop/Stand`

</details>

Codex source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-codex-copilot-gemini-argon-fullval-r2-20261018/results/shard-0856/106878960_174887073_ep22_bed/rollout_00/experiment_runs/run_f26ed792da014034809ce19953c9b9a6/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

**Pi, divergence decision 1**: `Turn<left><120>`. Visible-state claim: “Facing a kitchen stove and countertops. The target bed is not visible. Near-body lane forward is blocked by the stove, and right is blocked by kitchen cabinets.”

**Pi, final decision 61**: `Stop/Stand`. Visible-state claim: “Fully seated on the target bed with the bed corner visible at the bottom left and legs resting in front on the rug. Near-body lane forward is clear.”

<details><summary>Pi complete action chain (consecutive repeats compressed)</summary>

`Turn<left><120>` → `Walk<forward><fast>` → `Side step<right><0.40>` → `Turn<right><20>` → `Walk<forward><fast>` ×3 → `Turn<left><45>` → `Turn<left><90>` → `Turn<right><120>` → `Turn<right><60>` → `Turn<left><120>` ×2 → `Walk<forward><fast>` → `Turn<right><90>` → `Turn<right><120>` → `Turn<right><25>` → `Turn<left><15>` → `Side step<left><0.40>` → `Turn<left><15>` → `Walk<forward><fast>` ×2 → `Turn<left><90>` → `Walk<forward><fast>` ×6 → `Turn<left><60>` → `Walk<forward><fast>` ×2 → `Turn<right><35>` → `Turn<left><30>` → `Side step<left><0.50>` ×2 → `Walk<forward><fast>` ×2 → `Turn<left><60>` → `Turn<left><20>` → `Walk<forward><fast>` → `Side step<right><0.30>` → `Walk<forward><fast>` → `Side step<right><0.40>` → `Walk<forward><fast>` → `Turn<right><25>` → `Walk<forward><fast>` ×2 → `Turn<left><40>` → `Walk<forward><fast>` ×3 → `Walk<forward><normal>` ×2 → `Turn<left><90>` → `Turn<left><25>` → `Step back<0.20>` → `Sit down<0.55>` ×3 → `Stop/Stand`

</details>

Pi source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-pi-copilot-gemini-argon-fullval-r2-20261018/results/shard-0856/106878960_174887073_ep22_bed/rollout_00/experiment_runs/run_d9bd16641ffa4c289483cc151777915c/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

Interpretation boundary: distance/contact results are evaluator facts. The quoted visible-state descriptions are model claims. Images, orientation, contact progression, and recovery behavior must be read together before assigning a causal failure label.

---

## C075: gemini / both success

Task: scene `105515379_173104395`, episode `29`, target **chair**. Shard `shard-0653`.

Exact common action prefix: **1** decisions. The next action is the first behavioral divergence; it is not automatically the cause of the outcome.

| Harness | Terminal fact | Actions | Requests | Sit calls | Final distance (m) | Active stop | Target ever visible (GT) | Collision-step fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Codex | Success | 18 | 20 | 0 | 0.000 | True | True | 0.706 |
| Pi | Success | 23 | 24 | 0 | 0.000 | True | True | 0.727 |


**Codex, divergence decision 2**: `Turn<left><30>`. Visible-state claim: “A beige sofa is directly in front/right, a brown chest of drawers is ahead to the left, and the target cream wingback chair is visible in the distance beyond the sofa. The near-body lane slightly to the left behind the sofa is clear.”

**Codex, final decision 18**: `Stop/Stand`. Visible-state claim: “The target cream wingback chair is directly in contact with the body at zero distance. The near-body lane ahead is blocked by the chair.”

<details><summary>Codex complete action chain (consecutive repeats compressed)</summary>

`Turn<right><90>` → `Turn<left><30>` ×2 → `Walk<forward><fast>` → `Turn<right><40>` → `Turn<right><25>` → `Turn<right><15>` → `Walk<forward><fast>` ×3 → `Turn<right><15>` → `Walk<forward><fast>` ×2 → `Turn<right><25>` → `Walk<forward><fast>` → `Turn<right><20>` → `Walk<forward><slow>` → `Stop/Stand`

</details>

Codex source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-codex-copilot-gemini-argon-fullval-r2-20261018/results/shard-0653/105515379_173104395_ep29_chair/rollout_00/experiment_runs/run_88b9defac9904e8a9befab06274fd72c/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

**Pi, divergence decision 2**: `Turn<right><90>`. Visible-state claim: “Facing a sofa directly in front, with a wingback armchair visible in the background beyond the sofa. Near-body lane is blocked on the right by the sofa, narrow passage on the left behind the sofa.”

**Pi, final decision 23**: `Stop/Stand`. Visible-state claim: “Body is directly touching the beige plaid wingback chair at zero distance. Near-body lane is occupied by the target chair.”

<details><summary>Pi complete action chain (consecutive repeats compressed)</summary>

`Turn<right><90>` ×2 → `Turn<left><15>` → `Turn<left><75>` → `Turn<right><60>` → `Turn<left><80>` → `Turn<left><25>` → `Walk<forward><fast>` → `Turn<right><70>` → `Turn<right><15>` → `Walk<forward><fast>` ×2 → `Turn<right><15>` → `Side step<right><0.25>` → `Walk<forward><fast>` ×5 → `Turn<right><25>` → `Walk<forward><normal>` → `Walk<forward><slow>` → `Stop/Stand`

</details>

Pi source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-pi-copilot-gemini-argon-fullval-r2-20261018/results/shard-0653/105515379_173104395_ep29_chair/rollout_00/experiment_runs/run_8fd8cc24f9dc45b4b6fc1da7da6341cf/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

Interpretation boundary: distance/contact results are evaluator facts. The quoted visible-state descriptions are model claims. Images, orientation, contact progression, and recovery behavior must be read together before assigning a causal failure label.

---

## C076: gemini / both fail

Task: scene `107734287_176000160`, episode `23`, target **chair**. Shard `shard-1063`.

Exact common action prefix: **4** decisions. The next action is the first behavioral divergence; it is not automatically the cause of the outcome.

| Harness | Terminal fact | Actions | Requests | Sit calls | Final distance (m) | Active stop | Target ever visible (GT) | Collision-step fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Codex | Stopped outside threshold | 20 | 21 | 0 | 2.123 | True | True | 0.211 |
| Pi | Stopped outside threshold | 20 | 22 | 0 | 2.600 | True | True | 0.316 |


**Codex, divergence decision 5**: `Walk<forward><fast>`. Visible-state claim: “Facing a clear wooden corridor between the left wall/curtains and the black kitchen island on the right. Ahead in the living room, white armchairs and dining chairs are visible. The near-body forward lane is clear.”

**Codex, final decision 20**: `Stop/Stand`. Visible-state claim: “The body is directly touching the white armchair in front, with zero distance to the chair and the forward lane blocked by it.”

<details><summary>Codex complete action chain (consecutive repeats compressed)</summary>

`Turn<left><90>` ×2 → `Walk<forward><fast>` → `Turn<right><90>` → `Walk<forward><fast>` ×7 → `Turn<right><35>` → `Walk<forward><fast>` → `Walk<forward><normal>` → `Walk<forward><slow>` → `Side step<right><0.20>` → `Walk<forward><slow>` → `Turn<right><60>` → `Walk<forward><slow>` → `Stop/Stand`

</details>

Codex source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-codex-copilot-gemini-argon-fullval-r2-20261018/results/shard-1063/107734287_176000160_ep23_chair/rollout_00/experiment_runs/run_b04adcea9e2042db9a0554ff9f16e564/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

**Pi, divergence decision 5**: `Side step<left><0.30>`. Visible-state claim: “Looking down the corridor beside the black kitchen island on the right and wall on the left. Ahead in the living room are white armchairs, a bench, and dining chairs in the background. Right side of near-body lane is close to the counter edge.”

**Pi, final decision 20**: `Stop/Stand`. Visible-state claim: “Body is directly touching the back of the white chair with zero distance. Near-body lane forward is blocked by the target chair.”

<details><summary>Pi complete action chain (consecutive repeats compressed)</summary>

`Turn<left><90>` ×2 → `Walk<forward><fast>` → `Turn<right><90>` → `Side step<left><0.30>` → `Walk<forward><fast>` ×4 → `Turn<right><30>` → `Walk<forward><fast>` → `Side step<right><0.40>` ×2 → `Walk<forward><fast>` → `Turn<right><35>` → `Walk<forward><fast>` → `Turn<right><70>` → `Walk<forward><slow>` ×2 → `Stop/Stand`

</details>

Pi source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-pi-copilot-gemini-argon-fullval-r2-20261018/results/shard-1063/107734287_176000160_ep23_chair/rollout_00/experiment_runs/run_2bc7c66388d7420487fe22194b2c7ee4/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

Saved-image review sheet: [four recorded views](../assets/C076_sheet.jpg). These are existing observations, not a replay.

Interpretation boundary: distance/contact results are evaluator facts. The quoted visible-state descriptions are model claims. Images, orientation, contact progression, and recovery behavior must be read together before assigning a causal failure label.

---

## C077: gemini / both fail

Task: scene `104348010_171512832`, episode `26`, target **toilet**. Shard `shard-0382`.

Exact common action prefix: **4** decisions. The next action is the first behavioral divergence; it is not automatically the cause of the outcome.

| Harness | Terminal fact | Actions | Requests | Sit calls | Final distance (m) | Active stop | Target ever visible (GT) | Collision-step fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Codex | No valid sitting contact recorded | 14 | 15 | 2 | 0.000 | True | True | 0.000 |
| Pi | No valid sitting contact recorded | 13 | 14 | 2 | 0.000 | True | True | 0.000 |


**Codex, divergence decision 5**: `Side step<right><0.30>`. Visible-state claim: “The toilet is ahead and slightly to the right. The near-body lane is clear.”

**Codex, final decision 14**: `Stop/Stand`. Visible-state claim: “Fully seated on the toilet looking down at bent legs and checkered tile floor; the toilet is beneath us. The near-body lane ahead is clear.”

<details><summary>Codex complete action chain (consecutive repeats compressed)</summary>

`Turn<right><90>` → `Walk<forward><fast>` → `Turn<left><25>` → `Walk<forward><fast>` → `Side step<right><0.30>` → `Side step<right><0.20>` → `Walk<forward><normal>` → `Walk<forward><slow>` → `Turn<right><100>` → `Turn<right><80>` → `Step back<0.15>` → `Sit down<0.45>` ×2 → `Stop/Stand`

</details>

Codex source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-codex-copilot-gemini-argon-fullval-r2-20261018/results/shard-0382/104348010_171512832_ep26_toilet/rollout_00/experiment_runs/run_58bdba8cbc8b45d09d8e1b13f30f95c5/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

**Pi, divergence decision 5**: `Turn<right><25>`. Visible-state claim: “The toilet is visible close ahead and slightly to the right. The near-body lane is clear.”

**Pi, final decision 13**: `Stop/Stand`. Visible-state claim: “Fully seated on the toilet, looking down at bent legs with the toilet seat directly beneath. Task is complete.”

<details><summary>Pi complete action chain (consecutive repeats compressed)</summary>

`Turn<right><90>` → `Walk<forward><fast>` → `Turn<left><25>` → `Walk<forward><fast>` → `Turn<right><25>` → `Side step<right><0.25>` → `Side step<right><0.15>` → `Turn<right><90>` ×2 → `Step back<0.20>` → `Sit down<0.45>` ×2 → `Stop/Stand`

</details>

Pi source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-pi-copilot-gemini-argon-fullval-r2-20261018/results/shard-0382/104348010_171512832_ep26_toilet/rollout_00/experiment_runs/run_2897b3c88a5b4357889e460cd778802e/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

Interpretation boundary: distance/contact results are evaluator facts. The quoted visible-state descriptions are model claims. Images, orientation, contact progression, and recovery behavior must be read together before assigning a causal failure label.

---

## C078: gemini / both fail

Task: scene `107734254_176000121`, episode `1`, target **chair**. Shard `shard-1011`.

Exact common action prefix: **0** decisions. The next action is the first behavioral divergence; it is not automatically the cause of the outcome.

| Harness | Terminal fact | Actions | Requests | Sit calls | Final distance (m) | Active stop | Target ever visible (GT) | Collision-step fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Codex | Stopped outside threshold | 11 | 12 | 0 | 3.390 | True | False | 0.000 |
| Pi | Stopped outside threshold | 10 | 11 | 0 | 3.096 | True | True | 0.222 |


**Codex, divergence decision 1**: `Turn<left><60>`. Visible-state claim: “A patterned armchair is visible on the left behind a dark-framed glass door or partition, while a bright room with a small brown pouf is on the right. The immediate forward path is partially blocked by the partition frame.”

**Codex, final decision 11**: `Stop/Stand`. Visible-state claim: “The body is directly touching the beige armchair in front, with zero distance to the target chair.”

<details><summary>Codex complete action chain (consecutive repeats compressed)</summary>

`Turn<left><60>` → `Turn<right><90>` ×3 → `Turn<left><30>` ×2 → `Walk<forward><fast>` ×2 → `Walk<forward><normal>` → `Walk<forward><slow>` → `Stop/Stand`

</details>

Codex source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-codex-copilot-gemini-argon-fullval-r2-20261018/results/shard-1011/107734254_176000121_ep1_chair/rollout_00/experiment_runs/run_430b538837b94b5a8f4ba26ee57eab4e/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

**Pi, divergence decision 1**: `Turn<right><60>`. Visible-state claim: “Facing a dark partition/glass wall on the left and a bright floor with a small brown ottoman/cube ahead-right. Near-body lane has a partition on the left. Turning right to inspect the room for the chair.”

**Pi, final decision 10**: `Stop/Stand`. Visible-state claim: “The body is touching the beige armchair directly in front, with zero distance to the target chair. Stopping and standing to complete the task.”

<details><summary>Pi complete action chain (consecutive repeats compressed)</summary>

`Turn<right><60>` → `Turn<right><90>` ×2 → `Turn<left><80>` → `Walk<forward><fast>` ×3 → `Walk<forward><normal>` → `Walk<forward><slow>` → `Stop/Stand`

</details>

Pi source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-pi-copilot-gemini-argon-fullval-r2-20261018/results/shard-1011/107734254_176000121_ep1_chair/rollout_00/experiment_runs/run_7b36e179678d4da28a0238f1f8866e15/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

Interpretation boundary: distance/contact results are evaluator facts. The quoted visible-state descriptions are model claims. Images, orientation, contact progression, and recovery behavior must be read together before assigning a causal failure label.

---

## C079: gemini / both fail

Task: scene `108736689_177263340`, episode `9`, target **toilet**. Shard `shard-1109`.

Exact common action prefix: **13** decisions. The next action is the first behavioral divergence; it is not automatically the cause of the outcome.

| Harness | Terminal fact | Actions | Requests | Sit calls | Final distance (m) | Active stop | Target ever visible (GT) | Collision-step fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Codex | No valid sitting contact recorded | 18 | 19 | 2 | 0.078 | True | True | 0.588 |
| Pi | No valid sitting contact recorded | 18 | 19 | 3 | 0.114 | True | True | 0.529 |


**Codex, divergence decision 14**: `Step back<0.35>`. Visible-state claim: “Facing the shower partition and bathroom window with our back turned toward the toilet; the toilet is behind us (not visible in the current camera view), and the shower partition blocks the forward lane.”

**Codex, final decision 18**: `Stop/Stand`. Visible-state claim: “Fully seated on the toilet with the toilet bowl visible under the right leg and the bathroom floor and shower partition in front; the near-body lane in front is clear.”

<details><summary>Codex complete action chain (consecutive repeats compressed)</summary>

`Turn<right><90>` ×3 → `Walk<forward><fast>` ×4 → `Turn<left><45>` → `Walk<forward><fast>` ×3 → `Walk<forward><normal>` → `Turn<left><90>` → `Step back<0.35>` → `Step back<0.30>` → `Sit down<0.45>` → `Sit down<0.40>` → `Stop/Stand`

</details>

Codex source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-codex-copilot-gemini-argon-fullval-r2-20261018/results/shard-1109/108736689_177263340_ep9_toilet/rollout_00/experiment_runs/run_d5dc325a3a9a43b6846567aa44b6da61/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

**Pi, divergence decision 14**: `Step back<0.30>`. Visible-state claim: “Facing the shower partition with the toilet directly behind the body. The toilet is not visible in the current forward view. The near-body lane ahead is blocked by the shower partition.”

**Pi, final decision 18**: `Stop/Stand`. Visible-state claim: “Fully seated on the toilet with the toilet bowl visible underneath the right leg and zero distance to the toilet. The near-body lane ahead is clear.”

<details><summary>Pi complete action chain (consecutive repeats compressed)</summary>

`Turn<right><90>` ×3 → `Walk<forward><fast>` ×4 → `Turn<left><45>` → `Walk<forward><fast>` ×3 → `Walk<forward><normal>` → `Turn<left><90>` → `Step back<0.30>` → `Sit down<0.45>` ×3 → `Stop/Stand`

</details>

Pi source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-pi-copilot-gemini-argon-fullval-r2-20261018/results/shard-1109/108736689_177263340_ep9_toilet/rollout_00/experiment_runs/run_6d0bec09b2954c7397307172e2cace4f/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

Interpretation boundary: distance/contact results are evaluator facts. The quoted visible-state descriptions are model claims. Images, orientation, contact progression, and recovery behavior must be read together before assigning a causal failure label.

---

## C080: gemini / both fail

Task: scene `108736884_177263634`, episode `20`, target **tv**. Shard `shard-1208`.

Exact common action prefix: **2** decisions. The next action is the first behavioral divergence; it is not automatically the cause of the outcome.

| Harness | Terminal fact | Actions | Requests | Sit calls | Final distance (m) | Active stop | Target ever visible (GT) | Collision-step fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Codex | Stopped outside threshold | 19 | 20 | 0 | 0.327 | True | True | 0.167 |
| Pi | Stopped outside threshold | 19 | 20 | 0 | 0.324 | True | True | 0.167 |


**Codex, divergence decision 3**: `Turn<left><60>`. Visible-state claim: “Inside the bedroom with dresser on the left and bed on the right; the TV is not visible in the current view and the near-body lane is clear.”

**Codex, final decision 19**: `Stop/Stand`. Visible-state claim: “The TV is directly in front of the body above the dresser, and the body is pressed directly against the dresser beneath the TV with no forward space remaining.”

<details><summary>Codex complete action chain (consecutive repeats compressed)</summary>

`Walk<forward><fast>` ×2 → `Turn<left><60>` → `Walk<forward><fast>` → `Turn<right><35>` → `Turn<right><25>` → `Walk<forward><fast>` ×2 → `Side step<right><0.30>` ×2 → `Walk<forward><normal>` → `Walk<forward><slow>` → `Turn<left><80>` → `Side step<right><0.40>` → `Side step<right><0.30>` → `Walk<forward><slow>` ×3 → `Stop/Stand`

</details>

Codex source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-codex-copilot-gemini-argon-fullval-r2-20261018/results/shard-1208/108736884_177263634_ep20_tv/rollout_00/experiment_runs/run_ecf663c85f0b4a6b8988365043c1be13/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

**Pi, divergence decision 3**: `Turn<left><90>`. Visible-state claim: “Inside the bedroom facing the rug, armchairs, and bed. The dresser is on the left, where a TV might be mounted above it. The TV is not currently visible. The near-body lane is clear.”

**Pi, final decision 19**: `Stop/Stand`. Visible-state claim: “Facing the TV directly above the dresser, with the body touching the dresser directly beneath the TV at the closest possible horizontal distance.”

<details><summary>Pi complete action chain (consecutive repeats compressed)</summary>

`Walk<forward><fast>` ×2 → `Turn<left><90>` → `Turn<right><45>` → `Turn<right><35>` → `Walk<forward><fast>` ×2 → `Turn<left><90>` → `Turn<right><60>` → `Turn<right><25>` → `Walk<forward><fast>` ×2 → `Walk<forward><normal>` → `Walk<forward><slow>` → `Turn<right><25>` → `Walk<forward><normal>` → `Turn<left><80>` → `Walk<forward><slow>` → `Stop/Stand`

</details>

Pi source: `/gscratch/scrubbed/linjli/humanclaw/experiments/humanclaw-pi-copilot-gemini-argon-fullval-r2-20261018/results/shard-1208/108736884_177263634_ep20_tv/rollout_00/experiment_runs/run_5f9a2bf8d7d847939d5c52e4495e68d8/events.jsonl` (request/action summary retained in [selected trace evidence](../evidence/selected_trace_audit.jsonl.gz)).

Interpretation boundary: distance/contact results are evaluator facts. The quoted visible-state descriptions are model claims. Images, orientation, contact progression, and recovery behavior must be read together before assigning a causal failure label.
