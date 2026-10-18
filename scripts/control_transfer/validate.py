"""Operator integration checks. No LLM participates; --smoke is not a benchmark score."""

import argparse, base64, json, os
from pathlib import Path
from .specs import FAMILIES, spec
from .trusted.session import Session, atomic
from .trusted.verify import verdict


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--assets", type=Path, required=True)
    p.add_argument("--fly", type=Path, required=True)
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--reference", action="store_true")
    p.add_argument("--family", choices=FAMILIES)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    os.environ["CONTROL_ASSETS"] = str(a.assets.resolve())
    results = []
    for name in [a.family] if a.family else FAMILIES:
        for index in range(2):
            v = spec(name, index)
            family = v["family"]
            if family == "neural-fly":
                v["private_asset"] = str(a.fly.resolve())
            if a.smoke:
                for part in v["bank"]:
                    v["bank"][part] = v["bank"][part][:1]
            root = a.out / f"{name}-i{index:02d}"
            root.mkdir()
            atomic(root / "instance.json", v)
            policy = v["public"].get("default_policy")
            if a.reference and family == "spacecraft":
                from nonlinearbench.contract import REFERENCE

                policy = REFERENCE
            if family in ("g1", "linearbot"):
                policy = {
                    "npz_base64": base64.b64encode((a.assets / "reference" / f"{family}.npz").read_bytes()).decode()
                }
            s = Session(root / "session", v, wall_clock_s=14400)
            for turn in range(3):
                response = s.call(
                    "deploy",
                    {
                        "policy": policy,
                        "diagnosis": f"Operator integration repeat {turn + 1}: unchanged reference to check round accounting and feedback capture.",
                    },
                )
                if "error" in response:
                    raise RuntimeError(response)
            s.call("seal", {"round_id": 2, "summary": "Operator-only integration test; no model result."})
            s.finalize()
            result = verdict(s.root, root / "instance.json")
            if result["infra_error"]:
                raise RuntimeError("Integration or replay failed: " + str(root))
            nop = Session(root / "nop", v, render=False)
            nop.finalize()
            negative = verdict(nop.root, root / "instance.json")
            assert negative["success"] == 0 and negative["infra_error"] == 0
            result = {
                "task": name,
                "instance": index,
                "model_evaluation": False,
                "smoke_only": a.smoke,
                "verdict": result,
                "nop": negative,
                "videos": len(list(root.rglob("*.mp4"))),
                "feedback_images": len(list(root.rglob("frame-*.jpg"))),
            }
            results.append(result)
            atomic(a.out / "validation.json", results)
            print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
