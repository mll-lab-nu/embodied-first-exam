# P4 — Paired trajectories and failure evidence

The package contains **80 paired case cards**: five examples from each of four outcome quadrants in each native comparison. Every card includes endpoint metrics, the exact common action prefix, first differing action, terminal visible-state claims, complete action chains, and remote evidence paths. **24 pairs received a saved-image review**: 16 navigation pairs and eight interaction pairs, using 96 existing observations. Images were copied from recorded artifacts and their hashes verified; no trajectory was replayed or rendered.

The case sample is diagnostic and deliberately balanced across quadrants. Its label proportions must not be reported as population failure rates.

## How early do the behaviors diverge?

| Comparison | Paired tasks | Different first action | Median common prefix | Identical complete chains |
|---|---:|---:|---:|---:|
| r1 | 1,218 | 724 (59.44%) | 0 | 2 |
| r2 | 1,218 | 629 (51.64%) | 0 | 3 |
| r3 | 1,218 | 745 (61.17%) | 0 | 2 |
| Gemini | 1,217 | 367 (30.16%) | 2 | 2 |

Saved initial poses match in every pair. The nine identical-chain pairs also have matching outcomes. Most comparisons nevertheless diverge immediately or early. After divergence, “step 20 versus step 20” is generally not a comparison of the same observation or physical situation. The cards align the exact common prefix first and interpret later actions through their own observations.

## Population-level endpoint facts

The following counts come from all final episodes, not the selected cases.

| Condition | Navigation: stopped outside threshold | Interaction: Sit attempted, no valid contact recorded, then stopped | Interaction: no Sit, then stopped | Interaction: historical contact but terminal failure | No committed stop, either task type |
|---|---:|---:|---:|---:|---:|
| PSV r1 | 92 | 164 | 0 | 7 | 376 |
| Codex r1 | 186 | 525 | 45 | 2 | 0 |
| Pi r1 | 166 | 536 | 50 | 1 | 0 |
| Codex r2 | 171 | 323 | 39 | 15 | 1 |
| Pi r2 | 150 | 334 | 44 | 14 | 0 |
| Codex r3 max | 155 | 209 | 51 | 20 | 1 |
| Pi r3 xhigh | 149 | 209 | 39 | 23 | 0 |
| Codex Gemini | 142 | 292 | 17 | 3 | 37 |
| Pi Gemini | 152 | 335 | 10 | 1 | 52 |

These are mutually exclusive failure endpoints under the classification order in [terminal_outcomes.csv](tables/terminal_outcomes.csv). For example, a no-stop interaction episode with zero Sit is counted in “no committed stop,” not counted twice. The interaction-only Sit-behavior table uses all interaction tasks and therefore has a different zero-Sit denominator.

“No valid contact recorded” does not specify whether the underlying cause was alignment, seat choice, motion duration, height, or visual uncertainty. “Stopped outside threshold” includes both near misses and stopping far from the evaluator target.

## Findings supported by paired cases

### 1. Visual proximity is not reliable evidence of task completion

[C001, r1](cases/r1.md#c001-r1--codex-only) ends with the TV filling both views. Codex stops at **0.108 m** and succeeds; Pi at **0.245 m** and fails the 0.2 m navigation criterion. Both explicitly acknowledge uncertainty about contact. [C021, r2](cases/r2.md#c021-r2--codex-only) similarly ends at **0.083 versus 0.338 m** with a cabinet between the body and screen.

[C006, r1](cases/r1.md#c006-r1--pi-only) is an especially small threshold miss: Codex stops at **0.203 m**, while Pi reaches recorded zero distance. The plant appears close in both images. This is a calibration/completion-check issue, not evidence that the losing agent never found the object.

**Implication:** a completion decision should preserve uncertainty and account for blockers between the body and the target. A large target image alone is insufficient. The analysis does not propose exposing hidden evaluator distance to the policy.

### 2. Confident “zero distance” claims can refer to a different object or target interpretation

[C026, r2](cases/r2.md#c026-r2--pi-only) shows Codex approaching an orange rounded seat and declaring contact, but the evaluator target remains **1.443 m** away; Pi approaches wooden seating and ends **0.030 m** from the evaluator target. In [C016, r1](cases/r1.md#c016-r1--both-fail), both agents claim chair contact while recorded target distances are **1.681 and 2.819 m**.

[C061, Gemini](cases/gemini.md#c061-gemini--codex-only) contrasts a brown armchair with a wall-side wooden bench/chair interpretation; Pi's claim of zero distance disagrees with the **1.277 m** metric. [C066](cases/gemini.md#c066-gemini--pi-only) contrasts an exterior white flower box with a black potted plant; Codex declares zero distance while the evaluator reports **1.304 m**. [C076](cases/gemini.md#c076-gemini--both-fail) has two confident white-chair contact claims but distances **2.123 and 2.600 m**.

**Candidate explanation, moderate confidence:** target grounding or category/instance eligibility differs from the agent's interpretation. The image/metric discrepancy is certain; distinguishing model misidentification from benchmark object-label ambiguity requires target-annotation inspection. The evidence does not justify declaring every such case a hallucination.

### 3. Search and route failures remain distinct from contact failures

[C036, r2](cases/r2.md#c036-r2--both-fail) spends the full **100 actions** in both harnesses and ends **4.864 / 4.175 m** from a visible TV. Both terminal claims correctly say contact was not achieved. This differs from confident early completion.

[C041, r3](cases/r3.md#c041-r3--codex-only) has Codex near the TV at **0.138 m**, while Pi ends in a different room **21.700 m** away. [C046](cases/r3.md#c046-r3--pi-only) reverses the winner: Codex exhausts 100 actions around passages, ending **5.572 m** away, while Pi reaches the plant in **28 actions**.

[C062, Gemini](cases/gemini.md#c062-gemini--codex-only) is an interaction task whose Pi failure occurs before sitting: **100 actions, zero Sit**, ending near a hallway/bathroom doorway. Codex reaches and sits on the toilet successfully in **50 actions**.

**Implication:** the harness needs progress memory and route-recovery logic as well as interaction checks. These examples do not establish a consistent navigation advantage for either native runtime.

### 4. Repeating Sit is necessary in many cases, but is not sufficient

In [C022, r2](cases/r2.md#c022-r2--codex-only), both agents finish with two consecutive Sit calls and a seated-looking ego view. Codex has valid contact; Pi does not. The support surface and pelvis contact are mostly outside the ego view. Extra duration alone cannot explain this pair.

[C047, r3](cases/r3.md#c047-r3--pi-only) has three Sit calls in both trajectories, but different approach/orientation, backward motion, and requested heights (**0.65 versus 0.60 m**). Pi succeeds; Codex fails despite claiming a stable supported pose. [C067, Gemini](cases/gemini.md#c067-gemini--pi-only) has two Sit calls on both sides, again with different alignment and a backward adjustment on Pi's path.

[C027, r2](cases/r2.md#c027-r2--pi-only) has two total Sit calls for Codex versus four for Pi, with repositioning before the successful final sequence. [C042, r3](cases/r3.md#c042-r3--codex-only) has six total Sit calls and repositioning for Codex versus three for Pi. These suggest a useful interaction state sequence—approach, align, lower, check, adjust—without proving that any one additional action causes success.

**Implication:** retain the duration-aware action contract, then investigate support alignment, seat height, progress state, and evidence-sensitive stopping.

### 5. One Sit can succeed, so a fixed minimum is not a complete policy

[C002 and C007, r1](cases/r1.md) each have one Sit per harness, with opposite winners. Their terminal views all look lowered or seated, but only one side has evaluator-valid contact. These are counterexamples to a claim that one Sit must always fail or that a universal hard-coded repetition count solves the task.

The strong r1→r2 population shift still supports communicating duration and incompleteness. It supports a better action contract, not replacing state assessment with a fixed number of calls.

### 6. Both-success episodes reveal meaningful efficiency differences

The reviewed both-success cases reach similar task-valid endpoints through different paths: C011 uses **13 versus 12** actions, C031 **35 versus 38**, C051 **12 versus 16**, and C071 **42 versus 29**. Their full chains and request summaries are preserved. Population-level efficiency conclusions use all common-success pairs in [EFFICIENCY.md](EFFICIENCY.md), not these examples.

## Visual review ledger

Each entry links to four saved views: each harness at the first action divergence and at termination. Full action/claim evidence is in the phase case cards.

| Case | Review observation | Interpretation strength |
|---|---|---|
| [C001](assets/C001_sheet.jpg) | Both reach a TV; near-threshold distances differ | Endpoint difference certain; obstruction/contact interpretation moderate |
| [C002](assets/C002_sheet.jpg) | Both use one Sit beside a couch; contact outcomes differ | Sitting duration alone insufficient |
| [C006](assets/C006_sheet.jpg) | Both approach a plant near a table; Codex misses by 0.003 m | Threshold miss certain |
| [C007](assets/C007_sheet.jpg) | Similar couch/rug scene and one Sit; opposite contact outcomes | Hidden support contact cannot be judged from image alone |
| [C011](assets/C011_sheet.jpg) | Both reach the same potted palm; different final proximity | Both-success efficiency example |
| [C016](assets/C016_sheet.jpg) | Different chair-like objects, both far from metric target | Grounding/annotation ambiguity candidate |
| [C021](assets/C021_sheet.jpg) | TV fills both views with cabinet obstruction | Completion calibration candidate |
| [C022](assets/C022_sheet.jpg) | Both appear seated after two Sit calls; pelvis support mostly hidden | Contact/alignment ambiguity |
| [C026](assets/C026_sheet.jpg) | Orange rounded seat versus wooden seating | Grounding/annotation ambiguity candidate |
| [C027](assets/C027_sheet.jpg) | Different bed approaches and seated endpoints | Repositioning candidate, not isolated effect |
| [C031](assets/C031_sheet.jpg) | Both reach plant foliage/pot from different approaches | Both-success efficiency example |
| [C036](assets/C036_sheet.jpg) | Both still distant from TV at the action limit | Search/route progress failure supported |
| [C041](assets/C041_sheet.jpg) | Codex near TV; Pi ends in another room | Search/route divergence supported |
| [C042](assets/C042_sheet.jpg) | Both appear seated near a couch/fireplace; outcomes differ | Support/contact issue; recovery candidate |
| [C046](assets/C046_sheet.jpg) | Codex ends in passage; Pi reaches plant | Search/route divergence supported |
| [C047](assets/C047_sheet.jpg) | Both seated near bed but different orientations/heights | Alignment/height candidate |
| [C051](assets/C051_sheet.jpg) | Both close to same TV, 12 versus 16 actions | Both-success efficiency example |
| [C056](assets/C056_sheet.jpg) | Codex close but blocked by TV cabinet; Pi elsewhere | Different failure mechanisms in a both-fail pair |
| [C061](assets/C061_sheet.jpg) | Armchair versus bench/chair interpretation | Grounding/annotation ambiguity candidate |
| [C062](assets/C062_sheet.jpg) | Codex reaches toilet; Pi remains around doorway without sitting | Navigation-before-interaction failure supported |
| [C066](assets/C066_sheet.jpg) | White flower box versus black potted plant | Grounding/annotation ambiguity candidate |
| [C067](assets/C067_sheet.jpg) | Both lowered beside bed, different orientation/repositioning | Support/alignment candidate |
| [C071](assets/C071_sheet.jpg) | Both reach wall TV, different route lengths | Both-success efficiency example |
| [C076](assets/C076_sheet.jpg) | Both approach white seating but remain far from metric target | Grounding/annotation ambiguity candidate |

## Coverage and limits

The 80 cards cover all requested quadrants, but are not 80 independently adjudicated causal diagnoses. All 80 received automated metric/trace comparison; 24 received image review. The image review uses selected observations, not full videos. Provider internals, hidden reasoning beyond recorded outputs, and hypothetical alternative actions are not reconstructed.

Full population behavioral flags are available in [trajectory_features.csv](tables/trajectory_features.csv). A Walk with less than 0.02 m horizontal displacement is a low-motion flag; two consecutive turns of opposite sign are a reversal flag. Normal careful navigation can produce both. These features must not be presented as validated failure labels.

Case files: [r1](cases/r1.md), [r2](cases/r2.md), [r3](cases/r3.md), [Gemini](cases/gemini.md). Index: [case_index.csv](tables/case_index.csv).
