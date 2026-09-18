"""Independent cross-family route checks and common-scale geometry figures."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import trimesh
from .family_motion import OUTPUT,FAMILIES
from .family_geometry import evaluate
from .inverse_window import SolidOracle,save,sha


def cross_check(output=OUTPUT):
    output=Path(output);reports=[]
    for geometry in FAMILIES:
        folder=output/geometry;oracle=SolidOracle(folder/'assets')
        for motion in FAMILIES:
            trace=json.loads((output/motion/'ik_before_geometry.json').read_text())
            result=evaluate(oracle,[row['ball_pose'] for row in trace['frames']],resolution=.0004)
            reports.append(dict(geometry_family=geometry,motion_family=motion,**result))
            print(geometry,motion,'collision',result['collision_found'],flush=True)
    passed=all(r['collision_found']==(r['geometry_family']!=r['motion_family']) for r in reports)
    report=dict(passed=passed,tests=reports,unique_solution_proven=False,
        scope='Finite transfer tests of complete object pose routes in cage coordinates, including placement; robot reachability is not counted as a mechanism failure',
        source_sha256={f:{'ik':sha(output/f/'ik_before_geometry.json'),'assets':sha(output/f/'assets/sha256.json')} for f in FAMILIES})
    save(output/'cross_family_checks.json',report)
    if not passed:raise ValueError('A different family motion also passes; review distinction')
    return report


def figures(output=OUTPUT):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    output=Path(output);fig=plt.figure(figsize=(15,6),layout='constrained')
    for i,f in enumerate(FAMILIES):
        mesh=trimesh.load(output/f/'assets/cage.obj',force='mesh');v=mesh.vertices*1000
        ax=fig.add_subplot(1,3,i+1,projection='3d')
        ax.plot_trisurf(v[:,0],v[:,1],v[:,2],triangles=mesh.faces,color='#b79064',linewidth=0,antialiased=True,shade=True)
        ax.set(xlim=(-85,240),ylim=(-100,100),zlim=(-125,180),xlabel='X / mm',ylabel='Y / mm',zlabel='Z / mm',title=f'{chr(65+i)}: {f}')
        ax.set_box_aspect((325,200,305));ax.view_init(elev=18,azim=-35)
    fig.savefig(output/'cage_comparison.png',dpi=160);plt.close(fig)
    fig=plt.figure(figsize=(15,5),layout='constrained')
    for i,f in enumerate(FAMILIES):
        trace=json.loads((output/f/'ik_before_geometry.json').read_text())
        path=np.array(trace['proposed_path'])*np.r_[np.full(3,1000),np.ones(4)]
        seed=np.array(trace['seed_path'])*np.r_[np.full(3,1000),np.ones(4)]
        ax=fig.add_subplot(1,3,i+1,projection='3d')
        ax.plot(seed[:,0],seed[:,1],seed[:,2],color='#a4a9aa',label='Seed center route')
        ax.plot(path[:,0],path[:,1],path[:,2],'-o',color='#16857d',label='Family center route',markersize=3)
        ax.set(xlim=(20,360),ylim=(-25,140),zlim=(-25,60),xlabel='X / mm',ylabel='Y / mm',zlabel='Z / mm',title=f'{chr(65+i)}: center trajectory')
        ax.set_box_aspect((340,165,85));ax.view_init(elev=24,azim=-60);ax.legend(fontsize=8)
    fig.savefig(output/'motion_comparison.png',dpi=160);plt.close(fig)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['cross-check','figures']);p.add_argument('--output',type=Path,default=OUTPUT);a=p.parse_args()
    if a.action=='cross-check':cross_check(a.output)
    else:figures(a.output)


if __name__=='__main__':main()
