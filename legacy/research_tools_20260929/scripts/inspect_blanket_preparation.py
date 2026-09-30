"""Inspect recorded Blanket particles without rerunning or changing physics.

Older recordings lack full support tables. They can locate velocity hotspots,
but cannot retroactively prove a per-tick binding/contact history.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from topogym.evaluation.cloth_diagnostics import ClothParticleDiagnostics
from topogym.utils.io import relative_file, sha256_file, write_json_atomic


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--last-seconds", type=float, default=2., help="Final window; 0 processes the full trace")
    args = parser.parse_args()
    if not np.isfinite(args.last_seconds) or args.last_seconds < 0:
        parser.error("last-seconds must be finite and nonnegative")
    source, output = args.run.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    metadata = dict(status="in_progress", kind="recorded_particle_analysis_not_physics_rerun",
        source=str(source), last_seconds=args.last_seconds, sources={},
        implementation_sha256={str(p): sha256_file(p) for p in (Path(__file__),
            Path(__file__).resolve().parents[1]/"topogym/evaluation/cloth_diagnostics.py")})
    write_json_atomic(output/"report.json", metadata)
    try:
        report = json.loads((source/"report.json").read_text())
        identity = json.loads((source/"identity.json").read_text())
        rows = [json.loads(s) for s in (source/"ticks.jsonl").read_text().splitlines()]
        with np.load(relative_file(source, rows[0]["particle_file"]), allow_pickle=False) as archive:
            birth = archive["positions"][rows[0]["particle_row"]]
        if rows[0]["stage"] != "flat_birth" or np.ptp(birth[:, 2]) > 1e-8:
            raise ValueError("Historical UV reconstruction requires recorded flat birth")
        parameters, profile = identity["parameters"], report["profile"]
        uv = birth[:, :2]-np.asarray(parameters["center_xy_m"])
        table = identity["scene"]["env"]["world"]["table"]
        bounds = np.array(table["pos"][:2])+np.array([[-1], [1]])*np.array(table["size"][:2])/2
        diagnostic = ClothParticleDiagnostics(uv, width=parameters["width_m"],
            panel_fractions=profile["panel_fractions"], crease_band=profile["crease_band_m"],
            particle_size=parameters["particle_size_m"], table_z=table["pos"][2]+table["size"][2]/2,
            table_bounds=bounds, particle_start=None,
            speed_limit=report["preparation"]["settled_maximum_speed_m_s"])
        start = rows[-1]["sim_time_s"]-args.last_seconds if args.last_seconds else -1
        selected = [r for r in rows if r["sim_time_s"] >= start-1e-9]
        groups = {}
        for row in selected:
            groups.setdefault(row["particle_file"], []).append(row)
        samples = []
        with (output/"ticks.jsonl").open("x") as stream:
            for name, group in groups.items():
                path = relative_file(source, name)
                metadata["sources"][name] = sha256_file(path)
                with np.load(path, allow_pickle=False) as archive:
                    positions, velocities, ticks = archive["positions"], archive["velocities"], archive["physics_step"]
                for row in group:
                    index = row["particle_row"]
                    if ticks[index] != row["physics_step"]:
                        raise ValueError("Recorded tick/chunk index mismatch")
                    value = diagnostic.sample(row["physics_step"], row["sim_time_s"], row["stage"], positions[index], velocities[index])
                    samples.append(value)
                    stream.write(json.dumps(value, allow_nan=False)+"\n")
        np.savez_compressed(output/"particle_summary.npz", material_uv_m=uv,
            panel_id=diagnostic.panels, released_exceedance_samples=diagnostic.released_exceedances,
            maximum_speed_m_s=diagnostic.peak_speed)
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(12, 4), constrained_layout=True)
        color = axes[0].scatter(uv[:, 0]*1000, uv[:, 1]*1000,
            c=diagnostic.released_exceedances/max(1, diagnostic.released_samples), s=6, cmap="magma", vmin=0, vmax=1)
        for crease in diagnostic.creases:
            axes[0].axhline(crease*1000, color="cyan", linewidth=.6, alpha=.65)
        axes[0].set(xlabel="Material u (mm)", ylabel="Material v (mm)",
            title=f"Fraction of released samples above {diagnostic.speed_limit*1000:g} mm/s", aspect="equal")
        fig.colorbar(color, ax=axes[0], label="Fraction (fixed material coordinates)")
        times = [s["sim_time_s"] for s in samples]
        for key, label in [("maximum_speed_m_s", "max"), ("p99_speed_m_s", "P99"), ("mean_speed_m_s", "mean")]:
            axes[1].plot(times, [s[key]*1000 for s in samples], label=label)
        axes[1].axhline(diagnostic.speed_limit*1000, color="gray", linestyle="--", label="max-speed gate")
        axes[1].set(xlabel="Recorded simulation time (s)", ylabel="Speed (mm/s)", title="Recorded velocity; no resimulation")
        axes[1].legend()
        fig.savefig(output/"hotspots.png", dpi=160)
        plt.close(fig)
        summary = diagnostic.summary()
        hottest = max(samples, key=lambda r:r["maximum_speed_m_s"])
        summary.update(maximum_speed_event=hottest,
            first_tick=selected[0]["physics_step"], last_tick=selected[-1]["physics_step"],
            time_window_s=[selected[0]["sim_time_s"],selected[-1]["sim_time_s"]])
        write_json_atomic(output/"summary.json", summary)
        for name in ("report.json", "identity.json", "ticks.jsonl", rows[0]["particle_file"]):
            metadata["sources"][name] = sha256_file(source/name)
        metadata.update(status="passed", samples=len(samples),
            material_coordinates="Derived from saved flat birth XY and declared translation",
            unavailable=["actual support table", "per-tick binding changes", "engine constraint rest arrays", "substep corrections", "contact forces"],
            no_root_cause_claim=True)
    except BaseException as error:
        metadata.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        write_json_atomic(output/"report.json", metadata)


if __name__ == "__main__":
    main()
