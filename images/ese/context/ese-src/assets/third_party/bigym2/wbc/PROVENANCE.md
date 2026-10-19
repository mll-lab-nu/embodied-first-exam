# Provenance of the vendored GR00T-WBC runtime

Upstream: <https://github.com/NVlabs/GR00T-WholeBodyControl>, commit
`021df739f0b36e514399f0030e3a195683a46383`, package `decoupled_wbc`.
Code is Apache-2.0 (the repository's LICENSE dual-licenses source under
Apache-2.0 and model weights under the NVIDIA Open Model License; the
weights are covered by THIRD_PARTY_NOTICES.md section 1).

| File here | Upstream path | sha256 of the upstream file | Status |
|---|---|---|---|
| `gear_wbc_utils.py` | `decoupled_wbc/control/utils/gear_wbc_utils.py` | `0224a06cedafb896f950bb768d120193abcd50081f5858e1dfe5376225aa8478` | byte-identical |
| `g1_gear_wbc.yaml` | `decoupled_wbc/sim2mujoco/resources/robots/g1/g1_gear_wbc.yaml` | `31226a224ca8450e89d9ce17d5cb31c052192a9cbfedc8d145f1cb95627ac7a2` | byte-identical |
| `g1_gear_wbc_policy.py` | `decoupled_wbc/control/policy/g1_gear_wbc_policy.py` | `833bc58c7bacabf8634a9d458da821bc86b179af8420075ad9824e317d054e3e` | modified, see below |

Not vendored: `decoupled_wbc/control/base/policy.py` (an abstract base
class whose only behaviour, storing the observation, is inlined) and the
package `__init__.py` / `version.py`.

## Edits to `g1_gear_wbc_policy.py`

- Imports: `from decoupled_wbc...` became package-relative; `torch` is no
  longer imported. The class no longer inherits `Policy`; its no-op
  `reset()` / `close()` hooks are defined inline.
- `__init__`: the two ONNX paths are used as given (upstream joined them onto
  its own `sim2mujoco/resources/robots/g1/` directory); `gait_indices` is a
  float32 numpy array instead of a torch tensor; `obs_tensor` starts as
  `None`.
- `load_onnx_policy`: the session is created with
  `intra_op_num_threads = inter_op_num_threads = 1`; the inference closure takes and
  returns numpy arrays instead of torch tensors.
- `compute_observation`: the gait clock advances with `np.remainder`; the
  torch `foot_indices` / `clock_inputs` computation was dropped because its
  result never entered the observation (the upstream lines that would have
  written it are commented out).
- `set_observation`: `obs_tensor` is `obs_buffer[None, :]` instead of
  `torch.from_numpy(obs_buffer).unsqueeze(0)`.
- `get_action`: no `torch.no_grad()` block; `.detach().numpy()` dropped.
- `handle_keyboard_button` (keyboard teleop) removed.

Equivalence: the observation layout, history buffer, command handling,
Balance/Walk selection threshold and all constants are unchanged; bigym's
40 protocol fingerprints and deterministic rollouts are byte-identical
before and after vendoring.
