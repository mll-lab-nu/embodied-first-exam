"""Plot the crossed geometry candidates at a shared physical scale."""
import argparse
import json
from pathlib import Path

import numpy as np


def diagram(folder):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle
    from .geometry import COLORS
    manifest=json.loads((folder/"manifest.json").read_text())
    fig,axes=plt.subplots(3,3,figsize=(12,12),layout="constrained")
    for ax,record in zip(axes.flat,manifest["representatives"]):
        p=record["parameters"]
        radius=p["ring_inner_radius_m"]*1000
        # Goal-aligned cross section, not a rendering of the initially flared wires.
        ax.add_patch(Circle((0,0),radius+8,facecolor="#ae623c",edgecolor="#743e24",lw=.8))
        ax.add_patch(Circle((0,0),radius,facecolor="#f4f5f5",edgecolor="#743e24",lw=.8))
        ax.add_patch(Circle((0,0),12,facecolor="#34383c",edgecolor="#16191b",lw=.8))
        ax.add_patch(Circle((0,0),10.32,facecolor="#b2b0a0",edgecolor="none"))
        for i in range(p["fiber_count"]):
            angle=2*np.pi*i/p["fiber_count"]
            ax.add_patch(Circle((8*np.cos(angle),8*np.sin(angle)),1.2,
                facecolor=COLORS[i%len(COLORS)],edgecolor="#444444",lw=.3))
        ax.set(xlim=(-25,25),ylim=(-25,25),aspect="equal")
        ax.axis("off")
        ax.set_title(f"{p['family_id'].capitalize()} · {p['fiber_count']} wires\n"
                     f"Ring R = {radius:g} mm",fontsize=12)
        ax.text(0,-24,f"Actual radial clearance: {record['trunk_radial_clearance_m']*1000:.3f} mm",
                ha="center",va="center",fontsize=10)
    fig.suptitle("Density × aperture: nine candidate cross sections\n"
        "Same scale · jacket R 12 mm · wire R 1.2 mm · roots on R 8 mm circle\n"
        "Goal-aligned diagram; initial wires flare outward. Geometry checks only; robot execution pending.",fontsize=13)
    fig.savefig(folder/"density_radius_grid.png",dpi=180)
    fig.savefig(folder/"density_radius_grid.svg")
    plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder",type=Path)
    args=parser.parse_args()
    diagram(args.folder)


if __name__=="__main__":
    main()
