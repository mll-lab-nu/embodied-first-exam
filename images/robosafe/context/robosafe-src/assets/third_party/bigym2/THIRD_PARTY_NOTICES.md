# Third-Party Notices

BiGym 2.0 is distributed under the Apache License 2.0 (see [`LICENSE`](LICENSE)).
This file lists the third-party components redistributed inside this
repository, or pulled in as pinned dependencies, together with their upstream
origin and licensing terms.

Nothing in this file changes or supersedes the terms of the components it
describes. Where a component ships its own license file, that file is
authoritative; the vendored copy is named in each section.

Last reviewed: 2026-10-07.

## Summary

| # | Component | Path(s) in repo | License |
|---|-----------|-----------------|---------|
| 1 | GR00T Whole-Body Control policy weights (NVIDIA) | `bigym/loco/assets/GR00T-WholeBodyControl-{Balance,Walk}.onnx` | NVIDIA Open Model License |
| 2 | GR00T-WBC policy runtime (NVIDIA, vendored source) | `bigym/loco/adapters/_groot/` | Apache-2.0 |
| 3 | Unitree G1 body meshes (AMO MJCF packaging) | `bigym/envs/xmls/g1/meshes/` | Apache-2.0 (packaging); BSD-3-Clause (robot description) |
| 4 | Unitree G1 Dex1-1 / 5010 wrist meshes + MJCF | `bigym/envs/xmls/g1/` | BSD-3-Clause |
| 5 | 3D props — CC BY 4.0 group | `bigym/envs/xmls/props/{groceries,kitchen,board,pan,saucepan,spatula}/...` | CC BY 4.0 |
| 6 | 3D props — CC0 group | `bigym/envs/xmls/props/{cutlery,table,table_dishwasher,plate,mug,cutlery_tray}/...` | CC0 1.0 |
| 7 | Box prop | `bigym/envs/xmls/props/box/assets` | Apache-2.0 (procedural texture generated in-repo) |
| 8 | 3D assets from upstream BiGym | `bigym/envs/xmls/props/{dishwasher,dish_drainer,sandwich,cube}/` | see §8 |
| 9 | Upstream BiGym | this repository (fork base) | Apache-2.0 |
| 10 | Code adapted from mjlab | `typings/` | Apache-2.0 |

---

## 1. GR00T Whole-Body Control policy weights

- **Component**: `GR00T-WholeBodyControl` decoupled WBC G1 policy checkpoints
  (Balance and Walk experts), used by the `groot_wbc_g1` lower-body backend.
- **Path(s) in repo**:
  - `bigym/loco/assets/GR00T-WholeBodyControl-Balance.onnx`
  - `bigym/loco/assets/GR00T-WholeBodyControl-Walk.onnx`
- **Upstream URL**: <https://github.com/NVlabs/GR00T-WholeBodyControl>
  (weights at `decoupled_wbc/sim2mujoco/resources/robots/g1/policy/`)
- **Copyright**: NVIDIA Corporation & Affiliates.
- **License**: NVIDIA Open Model License Agreement (version dated
  2025-10-24). Upstream `LICENSE` states the repository is dual-licensed:
  source code under Apache-2.0, **model weights under the NVIDIA Open Model
  License**. Upstream ships the license text in a file named
  `NVIDIA Open Model License` next to the weights.
- **Verification**: the two `.onnx` files in this repository are MD5-identical
  to the upstream checkpoints
  (`409ca65a1937dfe2528bb604090fd2ae` Balance,
  `3856429cab4856cfa47cefe2d34cb7ca` Walk; checked 2026-09-02).
- **License text**: reproduced verbatim below, as required for
  redistribution of the Model.

<details>
<summary>NVIDIA Open Model License Agreement (full text)</summary>

```text
NVIDIA Open Model License Agreement

Last Modified: October 24, 2025

This NVIDIA Open Model License Agreement (the “Agreement”) is a legal agreement between the Legal Entity You represent, or if no entity is identified, You and NVIDIA Corporation and its Affiliates (“NVIDIA”) and governs Your use of the Models that NVIDIA provides to You under this Agreement. NVIDIA and You are each a “party” and collectively the “parties.”

NVIDIA models released under this Agreement are intended to be used permissively and enable the further development of AI technologies. Subject to the terms of this Agreement, NVIDIA confirms that:

Models are commercially usable.
You are free to create and distribute Derivative Models.
NVIDIA does not claim ownership to any outputs generated using the Models or Derivative Models.
By using, reproducing, modifying, distributing, performing or displaying any portion or element of the Model or Derivative Model, or otherwise accepting the terms of this Agreement, you agree to be bound by this Agreement.

Definitions. The following definitions apply to this Agreement:

"Derivative Model" means all (a) modifications to the Model, (b) works based on the Model, and (c) any other derivative works of the Model. An output is not a Derivative Model.

"Legal Entity" means the union of the acting entity and all other entities that control, are controlled by, or are under common control with that entity. For the purposes of this definition, "control" means (a) the power, direct or indirect, to cause the direction or management of such entity, whether by contract or otherwise, or (b) ownership of fifty percent (50%) or more of the outstanding shares, or (c) beneficial ownership of such entity.

“Model” means the machine learning model, software, checkpoints, learnt weights, algorithms, parameters, configuration files and documentation shared under this Agreement.

"NVIDIA Cosmos Model" means a multimodal Model shared under this Agreement

"Special-Purpose Model" means a Model that is only competent in a narrow set of purpose-specific tasks and should not be used for unintended or general-purpose applications

“You” or “Your” means an individual or Legal Entity exercising permissions granted by this Agreement.

Conditions for Use, License Grant, AI Ethics and IP Ownership.

Conditions for Use. The Model and any Derivative Model are subject to additional terms as described in Section 2 and Section 3 of this Agreement and govern Your use. If You institute copyright or patent litigation against any entity (including a cross-claim or counterclaim in a lawsuit) alleging that the Model or a Derivative Model constitutes direct or contributory copyright or patent infringement, then any licenses granted to You under this Agreement for that Model or Derivative Model will terminate as of the date such litigation is filed. If You bypass, disable, reduce the efficacy of, or circumvent any technical limitation, safety guardrail or associated safety guardrail hyperparameter, encryption, security, digital rights management, or authentication mechanism (collectively “Guardrail”) contained in the Model without a substantially similar Guardrail appropriate for your use case, your rights under this Agreement will automatically terminate. NVIDIA may indicate in relevant documentation that a Model is a Special-Purpose Model. NVIDIA may update this Agreement to comply with legal and regulatory requirements at any time and You agree to either comply with any updated license or cease Your copying, use, and distribution of the Model and any Derivative Model.

License Grant. The rights granted herein are explicitly conditioned on Your full compliance with the terms of this Agreement. Subject to the terms and conditions of this Agreement, NVIDIA hereby grants to You a perpetual, worldwide, non-exclusive, no-charge, royalty-free, revocable (as stated in Section 2.1) license to publicly perform, publicly display, reproduce, use, create derivative works of, make, have made, sell, offer for sale, distribute (through multiple tiers of distribution) and import the Model.

AI Ethics. Use of the Models under the Agreement must be consistent with NVIDIA’s Trustworthy AI terms found at https://www.nvidia.com/en-us/agreements/trustworthy-ai/terms/.

NVIDIA owns the Model and any Derivative Models created by NVIDIA. Subject to NVIDIA’s underlying ownership rights in the Model or its Derivative Models, You are and will be the owner of Your Derivative Models. NVIDIA claims no ownership rights in outputs. You are responsible for outputs and their subsequent uses. Except as expressly granted in this Agreement, (a) NVIDIA reserves all rights, interests and remedies in connection with the Model and (b) no other license or right is granted to you by implication, estoppel or otherwise.

Redistribution. You may reproduce and distribute copies of the Model or Derivative Models thereof in any medium, with or without modifications, provided that You meet the following conditions:

If you distribute the Model, You must give any other recipients of the Model a copy of this Agreement and include the following attribution notice within a “Notice” text file with such copies: “Licensed by NVIDIA Corporation under the NVIDIA Open Model License”;

If you distribute or make available a NVIDIA Cosmos Model, or a product or service (including an AI model) that contains or uses a NVIDIA Cosmos Model, use a NVIDIA Cosmos Model to create a Derivative Model, or use a NVIDIA Cosmos Model or its outputs to create, train, fine tune, or otherwise improve an AI model, you will include “Built on NVIDIA Cosmos” on a related website, user interface, blogpost, about page, or product documentation; and

You may add Your own copyright statement to Your modifications and may provide additional or different license terms and conditions for use, reproduction, or distribution of Your modifications, or for any such Derivative Models as a whole, provided Your use, reproduction, and distribution of the Model otherwise complies with the conditions stated in this Agreement.

Separate Components. The Models may include or be distributed with components provided with separate legal notices or terms that accompany the components, such as an Open Source Software License or other third-party license. The components are subject to the applicable other licenses, including any proprietary notices, disclaimers, requirements and extended use rights; except that this Agreement will prevail regarding the use of third-party Open Source Software License, unless a third-party Open Source Software License requires its license terms to prevail. “Open Source Software License” means any software, data or documentation subject to any license identified as an open source license by the Open Source Initiative (https://opensource.org), Free Software Foundation (https://www.fsf.org) or other similar open source organization or listed by the Software Package Data Exchange (SPDX) Workgroup under the Linux Foundation (https://www.spdx.org).

Trademarks. This Agreement does not grant permission to use the trade names, trademarks, service marks, or product names of NVIDIA, except as required for reasonable and customary use in describing the origin of the Model and reproducing the content of the “Notice” text file.

Disclaimer of Warranty. Unless required by applicable law or agreed to in writing, NVIDIA provides the Model on an “AS IS” BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied, including, without limitation, any warranties or conditions of TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A PARTICULAR PURPOSE. You are solely responsible for reviewing Model documentation, including any Special-Purpose Model limitations, and determining the appropriateness of using or redistributing the Model, Derivative Models and outputs. You assume any risks associated with Your exercise of permissions under this Agreement.

Limitation of Liability. In no event and under no legal theory, whether in tort (including negligence), contract, or otherwise, unless required by applicable law (such as deliberate and grossly negligent acts) or agreed to in writing, will NVIDIA be liable to You for damages, including any direct, indirect, special, incidental, or consequential damages of any character arising as a result of this Agreement or out of the use or inability to use the Model, Derivative Models or outputs (including but not limited to damages for loss of goodwill, work stoppage, computer failure or malfunction, or any and all other commercial damages or losses), even if NVIDIA has been advised of the possibility of such damages.

Indemnity. You will indemnify and hold harmless NVIDIA from and against any claim by any third party arising out of or related to your use or distribution of the Model, Derivative Models or outputs.

Feedback. NVIDIA appreciates your feedback, and You agree that NVIDIA may use it without restriction or compensation to You.

Governing Law. This Agreement will be governed in all respects by the laws of the United States and the laws of the State of Delaware, without regard to conflict of laws principles or the United Nations Convention on Contracts for the International Sale of Goods. The state and federal courts residing in Santa Clara County, California will have exclusive jurisdiction over any dispute or claim arising out of or related to this Agreement, and the parties irrevocably consent to personal jurisdiction and venue in those courts; except that, either party may apply for injunctive remedies or an equivalent type of urgent legal relief in any jurisdiction.

Trade and Compliance. You agree to comply with all applicable export, import, trade and economic sanctions laws and regulations, as amended, including without limitation U.S. Export Administration Regulations and Office of Foreign Assets Control regulations. These laws include restrictions on destinations, end-users and end-use.

Version Release Date: October 24, 2025
```

</details>

---

## 2. GR00T-WBC policy runtime (vendored source)

- **Component**: the `decoupled_wbc` G1 Gear-WBC policy runtime — the Python
  code that loads and steps the component 1 weights.
- **Path(s) in repo**: `bigym/loco/adapters/_groot/` —
  `g1_gear_wbc_policy.py` (modified), `gear_wbc_utils.py` (byte-identical),
  `g1_gear_wbc.yaml` (byte-identical). `PROVENANCE.md` in that directory
  lists the upstream paths, the sha256 of each original file and every edit
  made to the modified file (torch tensors replaced by numpy arrays, ONNX
  paths taken as given, single-threaded onnxruntime sessions, keyboard teleop
  handler removed).
- **Upstream URL**: <https://github.com/NVlabs/GR00T-WholeBodyControl>
  (commit `021df739f0b36e514399f0030e3a195683a46383`).
- **Copyright**: NVIDIA Corporation & Affiliates.
- **License**: Apache License 2.0 — source code, which upstream's dual-license
  notice places under Apache-2.0 (only model weights carry the NVIDIA Open
  Model License, §1). Redistributed under the same license with this notice;
  modifications are marked in `PROVENANCE.md` as Apache-2.0 §4(b) requires.
- **License text**: Apache-2.0, identical to this repository's
  [`LICENSE`](LICENSE).

---

## 3. Unitree G1 body meshes (AMO MJCF packaging)

- **Component**: Unitree G1 29-DoF humanoid body: the STL meshes of the
  pelvis, legs, waist, torso and arms, plus the MJCF body/inertial/actuator
  definitions above the wrist that the Dex1-1 scene in §4 inherits.
- **Path(s) in repo**: the body STL meshes under `bigym/envs/xmls/g1/meshes/`
  (every file there other than the Dex1/5010 meshes listed in §4),
  byte-identical to the source.
- **Upstream URL**: MJCF packaging by the AMO project,
  <https://github.com/OpenTeleVision/AMO>; underlying robot description from
  <https://github.com/unitreerobotics/unitree_ros>.
- **Copyright**: Jialong Li, Xuxin Cheng, Tianshu Huang, Xiaolong Wang
  (packaging); HangZhou YuShu TECHNOLOGY CO.,LTD ("Unitree Robotics")
  (robot description and meshes).
- **License**: Apache License 2.0 for the AMO packaging; the underlying
  Unitree robot description is BSD-3-Clause.
- **License text**: [`bigym/envs/xmls/g1/LICENSE`](bigym/envs/xmls/g1/LICENSE)
  (Apache-2.0, AMO authors) and
  [`bigym/envs/xmls/g1/LICENSE.unitree`](bigym/envs/xmls/g1/LICENSE.unitree)
  (BSD-3-Clause, Unitree Robotics).

---

## 4. Unitree G1 Dex1-1 grippers and 5010 wrists

- **Component**: Unitree Dex1-1 parallel gripper and official 5010 wrist
  meshes, and the G1 MJCF that mounts them on the arms.
- **Path(s) in repo**:
  - `bigym/envs/xmls/g1/g1_29dof_with_dex1_1.xml`
  - `bigym/envs/xmls/g1/meshes/Dex1_*.STL`, `dex1_col_*.stl`,
    `*_wrist_*_5010.STL`
- **Upstream URL**: <https://github.com/unitreerobotics/unitree_ros>
  (`robots/g1_description/g1_29dof_mode_15_with_dex1_1.urdf` and its meshes).
- **Copyright**: HangZhou YuShu TECHNOLOGY CO.,LTD ("Unitree Robotics").
- **License**: BSD-3-Clause, text in
  [`bigym/envs/xmls/g1/LICENSE.unitree`](bigym/envs/xmls/g1/LICENSE.unitree).
- **Modifications**: this project adds thin rubber-pad collision boxes on the
  finger inner faces and end-effector sites; they are distributed under the
  same terms.

---

## 5. 3D props — CC BY 4.0

Attribution is required. Per-model details, authors and source links are in
[`bigym/envs/xmls/3D_MODELS_ATTRIBUTION.md`](bigym/envs/xmls/3D_MODELS_ATTRIBUTION.md).

| Model | Path(s) | Author | Source |
|-------|---------|--------|--------|
| Groceries | `bigym/envs/xmls/props/groceries/assets` | tulex_art | <https://skfb.ly/6RCNy> |
| Kitchen set | `bigym/envs/xmls/props/kitchen/assets` | RedKit | <https://skfb.ly/6SXBW> |
| Kitchen utensils | `props/board/assets`, `props/pan/assets`, `props/saucepan/assets`, `props/spatula/assets`, `props/groceries/{detergent,soap,wine}/assets` | Nicolai Kilstrup | <https://skfb.ly/oFoUn> |

- **License**: Creative Commons Attribution 4.0 International —
  <https://creativecommons.org/licenses/by/4.0/>
- Some models were modified (re-meshed, decomposed for collision, re-scaled)
  for use in MuJoCo.

---

## 6. 3D props — CC0 1.0

| Model | Path(s) | Author | Source |
|-------|---------|--------|--------|
| Cutlery (knife, fork, spoon) | `props/cutlery/{knife,fork,spoon}/assets` | thebasemesh.com | <https://thebasemesh.com> |
| Tables | `props/table/assets`, `props/table_dishwasher/assets` | thebasemesh.com | <https://thebasemesh.com> |
| Plate | `props/plate/assets` | thebasemesh.com | <https://thebasemesh.com> |
| Mug | `props/mug/assets` | thebasemesh.com | <https://thebasemesh.com> |
| Cutlery tray | `props/cutlery_tray/assets` | thebasemesh.com | <https://thebasemesh.com> |

- **License**: CC0 1.0 Universal (public domain dedication) —
  <https://creativecommons.org/publicdomain/zero/1.0/>

---

## 7. Box prop — Apache-2.0 (procedural, in-repo)

- **Component**: Box 3D model, used by the `StoreBox` and `PickBox` tasks
  (`bigym/envs/pick_and_place.py`).
- **Path(s) in repo**: `bigym/envs/xmls/props/box/box.xml` (MuJoCo box
  primitives for both the visual and the collision geom) and
  `bigym/envs/xmls/props/box/assets/cardboard_procedural.png`, generated by
  `assets/make_cardboard_texture.py` (fixed seed, numpy/PIL, no external
  input).
- **License**: same as the repository (Apache-2.0). No third-party content.

---

## 8. 3D assets from upstream BiGym

These asset directories come from the upstream BiGym repository (§9,
Apache-2.0). The upstream attribution file lists no separate source for them,
so they are carried here under the upstream repository's terms. Corrections
to the record are welcome.

| Path | Contents |
|------|----------|
| `bigym/envs/xmls/props/dishwasher/assets` | textures + visual/collision OBJ meshes |
| `bigym/envs/xmls/props/dish_drainer/assets` | `drying_rack.png` + visual/collision OBJ meshes |
| `bigym/envs/xmls/props/sandwich/assets` | bread / cheese / tomato OBJ meshes + textures |
| `bigym/envs/xmls/props/cube/cube.xml` | MJCF only (procedural primitive), repository code |

---

## 9. Upstream BiGym

- **Component**: BiGym 2.0 is a hard fork of the original BiGym benchmark.
  The environments, task suite and props derive from it.
- **Path(s) in repo**: the repository as a whole (fork base).
- **Upstream URL**: <https://github.com/NeuracoreAI/bigym>
- **Paper**: N. Chernyadev, N. Backshall, X. Ma, Y. Lu, Y. Seo, S. James.
  *BiGym: A Demo-Driven Mobile Bi-Manual Manipulation Benchmark.*
  CoRL 2024. <https://arxiv.org/abs/2407.07788>
- **License**: Apache License 2.0 — see [`LICENSE`](LICENSE).

---

## 10. Code adapted from other projects

- **mjlab** (<https://github.com/mujocolab/mjlab>):
  `typings/generate_mujoco_stubs.sh` and `typings/postprocess_stubs.py` adapt
  the files of the same names. Apache License 2.0, identical to this
  repository's [`LICENSE`](LICENSE).
