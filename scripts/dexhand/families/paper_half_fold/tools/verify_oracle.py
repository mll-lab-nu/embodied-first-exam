"""Authoring check: the packaged runtime reproduces the accepted T06 episode bit for bit.

Compares, at every one of the 1,108 control boundaries, the full MuJoCo integration state and the paper's material
memory with the accepted episode's saved states, recomputes the accepted episode's own final hash with the original
hashing rule, and checks the compiled model against the frozen `model.mjb`. Not copied into task directories.

    DEXHAND_ASSET_DIR=$PWD/images/dexhand/assets/hand python scripts/dexhand/families/paper_half_fold/tools/verify_oracle.py \
        --trial ../artifacts/scene-expansion-50/evidence/paper-recovery-v3/trial-01 --out $OUT/paper-oracle-verify.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import mujoco
import numpy as np

FAMILY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FAMILY))
from runtime import STATE, Session  # noqa: E402

ORIGINAL_SOURCE_SHA256 = {
    "runtime.py": "188de2b83056fe4210bbf21710d7b25a00e967d77d5d0b767fb2394125c34f34",
    "scene.py": "45f0504f29521792036cc8ac4a39731bad3bac8e2908381c62783df23abd8517",
    "shell.py": "1a7a9278094829df2c9325ed30f41e96a8ed21d5b6e97262e5d59f35ec661cc7",
}


def legacy_sha(session, config) -> str:
    """The accepted runtime's state_sha rule (paper_recovery/runtime.py), evaluated on this session."""
    state = np.empty(mujoco.mj_stateSize(session.model, STATE))
    mujoco.mj_getState(session.model, session.data, state, STATE)
    digest = hashlib.sha256(state.astype("<f8").tobytes())
    digest.update(session.shell.rest_angles.astype("<f8").tobytes())
    digest.update(session.shell.plastic_work.astype("<f8").tobytes())
    digest.update(session.shell.plastic_strain.astype("<f8").tobytes())
    digest.update(json.dumps(config, sort_keys=True).encode())
    digest.update(json.dumps(ORIGINAL_SOURCE_SHA256, sort_keys=True).encode())
    digest.update(
        json.dumps(
            {
                "steps": session.steps,
                "hold": session.released_hold,
                "success": session.success,
                "failure": session.failure,
                "max_strain": session.shell.max_strain,
            },
            sort_keys=True,
        ).encode()
    )
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trial", type=Path, required=True)
    parser.add_argument("--controls", type=Path, help="defaults to the family's solution/trajectory.npz")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    trial = args.trial
    accepted = json.loads((trial / "result.json").read_text())
    instance = json.loads((trial / "instance.json").read_text())["config"]
    saved = np.load(trial / "saved-states.npz", allow_pickle=False)
    integration, material = saved["integration"], saved["material"]
    controls_path = args.controls or FAMILY / "solution" / "trajectory.npz"
    actions = np.load(controls_path, allow_pickle=False)["actions"]
    original_actions = np.load(trial / "controls.npz", allow_pickle=False)["actions"]
    started = time.monotonic()
    session = Session(hand="sharpa")
    frozen_mjb = hashlib.sha256((trial / "model.mjb").read_bytes()).hexdigest()
    result = {
        "trial": str(trial),
        "controls": str(controls_path),
        # The packaged rows are the accepted 1,108 rows plus 250 copies of the last one (a hold margin: the episode
        # ends at success, so they only matter when float32 rounding delays the end of the hold window).
        "controls_equal_accepted": bool(np.array_equal(actions[: len(original_actions)], original_actions)),
        "padding_rows": int(len(actions) - len(original_actions)),
        "padding_repeats_last_row": bool(np.all(actions[len(original_actions):] == original_actions[-1])),
        "config_equal_accepted": session.config == instance,
        "compiled_model_sha256": session.model_sha256,
        "frozen_model_mjb_sha256": frozen_mjb,
        "compiled_model_equal_frozen": session.model_sha256 == frozen_mjb,
    }
    state = np.empty(mujoco.mj_stateSize(session.model, STATE))
    mujoco.mj_getState(session.model, session.data, state, STATE)
    worst_state = float(np.max(np.abs(state - integration[0])))
    worst_material = 0.0
    result["initial_legacy_sha"] = legacy_sha(session, instance)
    first_success = None
    for i, row in enumerate(actions, 1):
        session.step(row)
        mujoco.mj_getState(session.model, session.data, state, STATE)
        worst_state = max(worst_state, float(np.max(np.abs(state - integration[i]))))
        mat = np.r_[session.shell.rest_angles, session.shell.plastic_strain, session.shell.plastic_work, session.shell.max_strain]
        worst_material = max(worst_material, float(np.max(np.abs(mat - material[i]))))
        if session.success and first_success is None:
            first_success = i
        if session.done:
            break
    status = session.status()
    result.update(
        rows=int(len(actions)),
        rows_executed=session.steps,
        boundary_states_compared=session.steps + 1,
        max_abs_integration_state_error=worst_state,
        max_abs_material_error=worst_material,
        first_success_row=first_success,
        success=bool(session.success),
        failure=session.failure,
        released_hold_steps=session.released_hold,
        features=session.features(),
        final_legacy_sha=legacy_sha(session, instance),
        accepted_initial_sha=accepted["initial_sha"],
        accepted_final_sha=accepted["final_sha"],
        packaged_state_sha=status["state_sha"],
        wall_s=time.monotonic() - started,
    )
    result["initial_sha_matches_accepted"] = result["initial_legacy_sha"] == accepted["initial_sha"]
    result["final_sha_matches_accepted"] = result["final_legacy_sha"] == accepted["final_sha"]
    result["bit_for_bit"] = bool(
        result["compiled_model_equal_frozen"]
        and result["controls_equal_accepted"]
        and result["padding_repeats_last_row"]
        and worst_state == 0.0
        and worst_material == 0.0
        and result["final_sha_matches_accepted"]
        and result["initial_sha_matches_accepted"]
    )
    session.close()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "features"}, indent=2))
    return 0 if result["bit_for_bit"] and result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
