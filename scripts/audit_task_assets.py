"""Audit cached reference geometry and unresolved baseline inputs."""
from __future__ import annotations

import hashlib
import argparse
import json
from pathlib import Path

import numpy as np
import trimesh

from topogym.tasks.catalog import TASK_IDS, load_card


def fetch_references(cache):
    """Cache the two pinned public meshes and their original viewer metadata."""
    from urllib.request import urlopen
    base="https://qinengwang-aiden.github.io/demos/constraint_demos/"
    cache.mkdir(parents=True,exist_ok=True)
    pinned=("35e40f140642310e64f587c528213fe60c64202bdababd654013f205b1602ed5",
            "15305d656b31248c13fad76089683a94f2720ce45ee22d3f4eacb7313eb6658b")
    for name,rel in (("claw_manifest.json","data/claw/manifest.json"),
                     ("threading_geometry.json","data/threading/geometry.json")):
        (cache/name).write_bytes(urlopen(base+rel,timeout=30).read())
    manifest=json.loads((cache/"claw_manifest.json").read_text())
    records=[]
    for i,expected in enumerate(pinned):
        item=next(p for p in manifest['pieces'] if p['id']==i)
        url=base+f"data/claw/piece-{i}.obj"
        data=urlopen(url,timeout=30).read()
        digest=hashlib.sha256(data).hexdigest()
        if digest!=expected or item['sha256']!=expected:
            raise ValueError("Public mesh changed; review the new reference version before accepting it")
        path=cache/f"piece-{i}.obj";path.write_bytes(data)
        records.append(dict(source_url=url,local_file=str(path.relative_to(cache.parents[3])),
            sha256=digest,source_origin=item['source_origin'],scale=item['scale']))
    (cache/"sources.json").write_text(json.dumps(records,indent=2)+"\n")


def missing_values(value, prefix="baseline"):
    if value is None:
        return [prefix]
    if isinstance(value, dict):
        return [key for k,v in value.items() for key in missing_values(v,f"{prefix}.{k}")]
    return []


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch",action="store_true",help="Download the pinned public references before auditing")
    args=parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    cache = root/".cache/topogym/first_night_references/wang"
    if args.fetch:fetch_references(cache)
    output = root/"runs/environment_bootstrap/asset_audit"
    output.mkdir(parents=True,exist_ok=True)
    pieces=[]
    for item in json.loads((cache/"sources.json").read_text()):
        source=root/item["local_file"]
        digest=hashlib.sha256(source.read_bytes()).hexdigest()
        if digest!=item["sha256"]: raise ValueError(f"Hash mismatch: {source}")
        mesh=trimesh.load(source,force="mesh",process=True)
        raw_vertex_count=len(mesh.vertices)
        # OBJ normal/UV seams can duplicate coincident vertices. Weld positions
        # for topology inspection without filling holes or changing faces.
        mesh.merge_vertices(merge_tex=True,merge_norm=True)
        mesh.vertices=(mesh.vertices-np.asarray(item["source_origin"]))*item["scale"]
        pieces.append(dict(**item,triangles=len(mesh.faces),vertices=len(mesh.vertices),
            raw_vertex_count=raw_vertex_count,topology_check="coincident-position weld, ignoring normal/UV seams",
            watertight=bool(mesh.is_watertight),winding_consistent=bool(mesh.is_winding_consistent),
            connected_components=len(mesh.split(only_watertight=False)),
            bounds_in_viewer_m=mesh.bounds.tolist(),extents_in_viewer_m=mesh.extents.tolist(),
            volume_in_viewer_m3=float(mesh.volume),geometry_checked_only=True,
            collision_proxy_verified=False,reference_route_verified=False))
    cards=[]
    for name in TASK_IDS:
        card=load_card(name)
        cards.append(dict(task_id=name,assets=card["assets"],
            missing_baseline_inputs=missing_values(card["baseline"]),
            next_probe=card["first_probe"],physics_qualified_by_this_audit=False))
    report=dict(scope="asset_and_parameter_readiness",claw_meshes=pieces,tasks=cards,
        threading_reference_cache=str((cache/"threading_geometry.json").relative_to(root)),
        missing_full_puzzle_assets=["cast_keyhole"],
        provisional_full_puzzle_reconstructions=["horseshoe_ring","hedgehog_in_cage","cast_coil"],
        limits="Claw OBJ validity does not establish collision decomposition, a robot grasp, or a physical solution.")
    (output/"report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
    print(json.dumps({"claw_meshes":pieces,"tasks_reviewed":len(cards)},indent=2))


if __name__=="__main__": main()
