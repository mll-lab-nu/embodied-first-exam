"""Infer connected family structures outside a conservative solved-motion sweep."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import numpy as np
import mujoco
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation
from scipy import ndimage
import trimesh
from .family_motion import OUTPUT, FAMILIES
from .inverse_window import SEED, Kinematics, SolidOracle, save, sha
from .geometry import HedgehogLayout, load_template, clearance_samples, write_body
from .plan_escape import interpolate


def union64(cells):
    import manifold3d as m
    from trimesh.iteration import reduce_cascade
    solids=[m.Manifold(m.Mesh64(vert_properties=np.asarray(c.vertices,dtype=np.float64),tri_verts=np.asarray(c.faces,dtype=np.uint64))) for c in cells]
    solid=reduce_cascade(lambda a,b:a+b,solids)
    if solid.status()!=m.Error.NoError:raise ValueError(f'Boolean failure: {solid.status()}')
    mesh=solid.to_mesh64()
    return trimesh.Trimesh(vertices=np.asarray(mesh.vert_properties),faces=np.asarray(mesh.tri_verts),process=False)


class Sweep:
    def __init__(self, folder):
        self.folder=Path(folder)
        with np.load(self.folder/'sweep.npz') as data:
            self.radii=data['radii'].copy();self.points=[data[f'points_{i}'].copy() for i in range(len(self.radii))]
        self.trees=[cKDTree(p) for p in self.points]
    def distance(self, points):
        points=np.asarray(points);distance=np.full(len(points),np.inf)
        for tree,r in zip(self.trees,self.radii):distance=np.minimum(distance,tree.query(points,workers=4)[0]-r)
        return distance


def make_sweep(folder):
    folder=Path(folder);trace=json.loads((folder/'ik_before_geometry.json').read_text())
    if (folder/'sweep.npz').exists():raise ValueError('Preserve existing sweep')
    layout=HedgehogLayout(load_template(),3.)
    points,radii=clearance_samples(layout,spacing=.001)
    groups=[points[:1],points[1:]];group_radii=[float(radii[0]),float(radii[1:].max())]
    kin=Kinematics();kin.q=np.array(trace['frames'][0]['qpos']);pose=kin.ball_pose()
    r=kin.cage_r*Rotation.from_quat(pose[3:]);p=kin.cage_origin+kin.cage_r.apply(pose[:3]);pads=[];pad_radius=0.
    for i in range(kin.model.ngeom):
        if kin.model.body(kin.model.geom_bodyid[i]).name not in ('left_finger','right_finger') or not kin.model.geom_contype[i]:continue
        if kin.model.geom_type[i]!=mujoco.mjtGeom.mjGEOM_BOX:raise ValueError('Unknown finger collider')
        size=kin.model.geom_size[i];counts=np.maximum(1,np.ceil(2*size/.002).astype(int));step=2*size/counts
        axes=[-a+(np.arange(n)+.5)*d for a,n,d in zip(size,counts,step)]
        local=np.array(np.meshgrid(*axes,indexing='ij')).reshape(3,-1).T
        world=local@kin.data.geom_xmat[i].reshape(3,3).T+kin.data.geom_xpos[i]+kin.mount
        pads.append(r.inv().apply(world-p));pad_radius=max(pad_radius,float(np.linalg.norm(step)/2))
    groups.append(np.concatenate(pads));group_radii.append(pad_radius)
    # Include every articulated Robotiq collision mesh in the fixed S2 grasp.
    # Cover convex solids by small cubical cells and their circumspheres.
    links=[];link_radius=0.
    from scipy.spatial import ConvexHull
    for i in range(kin.model.ngeom):
        name=kin.model.body(kin.model.geom_bodyid[i]).name
        if not name.startswith('r85_') or not kin.model.geom_contype[i]:continue
        if kin.model.geom_type[i]!=mujoco.mjtGeom.mjGEOM_MESH:continue
        mesh=kin.model.mesh(kin.model.geom_dataid[i])
        vertices=kin.model.mesh_vert[mesh.vertadr[0]:mesh.vertadr[0]+mesh.vertnum[0]].astype(float)
        hull=ConvexHull(vertices);lo=vertices.min(axis=0);hi=vertices.max(axis=0)
        counts=np.maximum(1,np.ceil((hi-lo)/.0025).astype(int));step=(hi-lo)/counts
        axes=[a+(np.arange(n)+.5)*d for a,n,d in zip(lo,counts,step)]
        local=np.array(np.meshgrid(*axes,indexing='ij')).reshape(3,-1).T
        rr=float(np.linalg.norm(step)/2);link_radius=max(link_radius,rr)
        inside=np.ones(len(local),dtype=bool)
        for equation in hull.equations:
            inside&=(local@equation[:3]+equation[3])<=rr
        local=local[inside]
        world=local@kin.data.geom_xmat[i].reshape(3,3).T+kin.data.geom_xpos[i]+kin.mount
        links.append(r.inv().apply(world-p))
    groups.append(np.concatenate(links));group_radii.append(link_radius)

    bound=max(.092,max(np.linalg.norm(p,axis=1).max() for p in groups));motion_step=.0007
    accumulated=[[] for _ in groups];n=0
    for i,(a,b) in enumerate(zip(trace['frames'][:-1],trace['frames'][1:])):
        for pose in list(interpolate(np.array(a['ball_pose']),np.array(b['ball_pose']),motion_step*.092/bound))[int(i>0):]:
            rot=Rotation.from_quat(pose[3:]);n+=1
            for j,(local,radius) in enumerate(zip(groups,group_radii)):
                world=rot.apply(local)+pose[:3]
                # Any excluded sphere is beyond every candidate cage cell.
                limit=radius+motion_step+.002
                keep=((world>np.array([-.09,-.095,-.125])-limit)&(world<np.array([.240,.095,.175])+limit)).all(axis=1)
                accumulated[j].append(world[keep])
    group_radii=np.array(group_radii)+motion_step+np.array([.0015,.0015,.0010,.0012])
    payload={f'points_{i}':np.concatenate(v).astype(np.float64) for i,v in enumerate(accumulated)}
    payload['radii']=group_radii;np.savez_compressed(folder/'sweep.npz',**payload)
    save(folder/'sweep_report.json',dict(poses=n,points=[len(payload[f'points_{i}']) for i in range(len(groups))],radii_m=group_radii.tolist(),
        material_motion_step_m=motion_step,maximum_grasp_geometry_radius_m=bound,
        ik_sha256=sha(folder/'ik_before_geometry.json'),sweep_sha256=sha(folder/'sweep.npz')))
    print(f'Sweep {n} poses, {[len(payload[f"points_{i}"]) for i in range(len(groups))]} covering spheres',flush=True)


def boxes_from_mask(mask, max_second=None):
    """Disjoint maximal rectangular blocks in a 3D occupancy grid."""
    remaining=mask.copy();blocks=[]
    for i,j,k in zip(*np.where(mask)):
        if not remaining[i,j,k]:continue
        endk=k+1
        while endk<mask.shape[2] and remaining[i,j,endk]:endk+=1
        endj=j+1
        while endj<mask.shape[1] and (max_second is None or endj-j<max_second) and remaining[i,endj,k:endk].all():endj+=1
        endi=i+1
        while endi<mask.shape[0] and remaining[endi,j:endj,k:endk].all():endi+=1
        remaining[i:endi,j:endj,k:endk]=False;blocks.append((i,endi,j,endj,k,endk))
    return blocks


def annular_cells(family, sweep):
    inner,outer=(.068,.078) if family=='helical_guide' else (.0585,.0675)
    rs=np.unique(np.r_[np.linspace(.033,inner,int(np.ceil((inner-.033)/.003))+1),np.linspace(inner,outer,5)])
    angles=np.linspace(-np.pi,np.pi,121);zs=np.linspace(-.12,.12,81)
    r=(rs[:-1]+rs[1:])/2;t=(angles[:-1]+angles[1:])/2;z=(zs[:-1]+zs[1:])/2
    R,T,Z=np.meshgrid(r,t,z,indexing='ij');centers=np.stack([R*np.cos(T),R*np.sin(T),Z],axis=-1)
    # Circumspheres cover each candidate convex annular voxel.
    radius=np.zeros(R.shape)
    for ir in (0,1):
        for it in (0,1):
            for iz in (0,1):
                rr,tt,zz=np.meshgrid(rs[ir:len(rs)-1+ir],angles[it:len(angles)-1+it],zs[iz:len(zs)-1+iz],indexing='ij')
                v=np.stack([rr*np.cos(tt),rr*np.sin(tt),zz],axis=-1)
                radius=np.maximum(radius,np.linalg.norm(v-centers,axis=-1))
    rims=np.abs(Z)>=.09
    twist=(Z/.09)*np.deg2rad(52) if family=='helical_guide' else np.zeros_like(Z)
    window_centers=np.deg2rad(np.arange(5)*72)
    open_region=np.zeros(R.shape,dtype=bool)
    for i,center in enumerate(window_centers):
        offset=twist
        if family=='oblique_gate' and i==0:offset=(Z/.09)*np.deg2rad(14)
        delta=(T-center-offset+np.pi)%(2*np.pi)-np.pi
        half=np.deg2rad(23 if i else 20)
        open_region|=abs(delta)<half
    stock=rims | ((R>inner)&~open_region)
    # Whole convex cells stay outside the positive sweep, with its built-in margin.
    ids=np.flatnonzero(stock);safe=np.zeros(stock.size,dtype=bool)
    gap=sweep.distance(centers.reshape(-1,3)[ids])-radius.ravel()[ids]
    safe[ids]=gap>0
    mask=safe.reshape(stock.shape)
    cells=[]
    for i,ii,j,jj,k,kk in boxes_from_mask(mask,max_second=3):
        vertices=[[rr*np.cos(tt),rr*np.sin(tt),zz] for rr in (rs[i],rs[ii]) for tt in (angles[j],angles[jj]) for zz in (zs[k],zs[kk])]
        cells.append(trimesh.convex.convex_hull(np.array(vertices)))
    return cells,dict(stock_voxels=int(stock.sum()),safe_voxels=int(mask.sum()),merged_cells=len(cells),outer_radius_m=outer)


def rectangular_gate_cells(sweep):
    xs=np.linspace(-.006,.226,117);ys=np.linspace(-.090,.090,91);zs=np.linspace(-.12,.17,146)
    x,y,z=[(a[:-1]+a[1:])/2 for a in (xs,ys,zs)]
    X,Y,Z=np.meshgrid(x,y,z,indexing='ij');centers=np.stack([X,Y,Z],axis=-1)
    gate=(X>=.214)
    rails=(abs(abs(Y)-.064)<.004)&(abs(abs(Z)-.105)<.004)
    stock=gate|rails
    radius=np.sqrt(np.diff(xs)[:,None,None]**2+np.diff(ys)[None,:,None]**2+np.diff(zs)[None,None,:]**2)/2
    ids=np.flatnonzero(stock);safe=np.zeros(stock.size,dtype=bool)
    safe[ids]=sweep.distance(centers.reshape(-1,3)[ids])-radius.ravel()[ids]>0
    cells=[]
    for i,ii,j,jj,k,kk in boxes_from_mask(safe.reshape(stock.shape)):
        lo=np.array([xs[i],ys[j],zs[k]]);hi=np.array([xs[ii],ys[jj],zs[kk]])
        cells.append(trimesh.creation.box(extents=hi-lo,transform=trimesh.transformations.translation_matrix((hi+lo)/2)))
    return cells,dict(stock_voxels=int(stock.sum()),safe_voxels=int(safe.sum()),merged_cells=len(cells))


def geometry(folder):
    folder=Path(folder);trace=json.loads((folder/'ik_before_geometry.json').read_text());family=trace['family']
    assets=folder/'assets'
    if assets.exists():raise ValueError('Preserve existing geometry')
    sweep=Sweep(folder);cells,report=annular_cells(family,sweep)
    if family=='staggered_gates':
        gates,details=rectangular_gate_cells(sweep);cells+=gates;report['second_gate']=details
    # Give adjacent polar grid cells 30 micrometres of shared material;
    # differently merged angular sectors otherwise meet only numerically.
    # Final solids receive an independent clearance certificate after this step.
    padding=np.array(np.meshgrid(*[[-.00003,.00003]]*3,indexing='ij')).reshape(3,-1).T
    cells=[trimesh.convex.convex_hull((c.vertices[:,None,:]+padding[None,:,:]).reshape(-1,3)) for c in cells]
    report['cell_seam_padding_m']=.00003
    print(f'{family}: union {len(cells)} convex cells',flush=True)
    union=union64(cells)
    components=sorted(union.split(),key=lambda m:-abs(m.volume))
    # Disconnected remnants are not legitimate cage members; retain only cells
    # belonging to the main connected component, then recompute the exact union.
    if sum(m.volume>1e-10 for m in components)>1:
        main=components[0]
        from trimesh.proximity import signed_distance
        keep=signed_distance(main,np.array([c.center_mass for c in cells]))>-.000001
        discarded=[c for c,k in zip(cells,keep) if not k]
        report['discarded_disconnected_cells']=len(discarded);report['discarded_disconnected_volume_m3']=sum(abs(c.volume) for c in discarded)
        cells=[c for c,k in zip(cells,keep) if k]
        union=union64(cells);components=sorted(union.split(),key=lambda m:-abs(m.volume))
    # A connected solid may have separate inward-facing shells of enclosed
    # air cavities. Preserve these negative-volume boundaries in the visual;
    # they are not disconnected pieces of cage material.
    extra=sum(max(float(m.volume),0.) for m in components[1:])
    if extra>1e-10 or not union.is_watertight:raise ValueError(f'Not a connected watertight cage: {len(components)}, {extra}')
    report['positive_material_components']=int(sum(m.volume>1e-10 for m in components))
    report['enclosed_void_shells']=int(sum(m.volume<0 for m in components))
    report['enclosed_void_volume_m3']=sum(-float(m.volume) for m in components if m.volume<0)
    mesh=union
    if family=='staggered_gates' and mesh.bounds[1,0]<.224:raise ValueError('Second gate disconnected')
    if mesh.bounds[0,2]>-.119 or mesh.bounds[1,2]<.119:raise ValueError('Carving lost a cage end ring')
    assets.mkdir()
    for src in (SEED/'assets').glob('hedgehog*'):
        if src.is_file():shutil.copy2(src,assets/src.name)
    shutil.copy2(SEED/'assets/template.json',assets/'template.json')
    body=write_body(assets,'cage',mesh,cells,(.2,.1,.04,1),2700.,finish='wood')
    report.update(family=family,cage=body,connected=True,watertight=True,hedgehog_geometry_preserved=True,
        maximum_radial_extent_m=float(np.linalg.norm(mesh.vertices[:,:2],axis=1).max()),
        ik_sha256=sha(folder/'ik_before_geometry.json'),sweep_sha256=sha(folder/'sweep.npz'))
    save(assets/'asset_report.json',report)
    save(assets/'sha256.json',{p.name:sha(p) for p in sorted(assets.iterdir()) if p.is_file() and p.name!='sha256.json'})
    print(json.dumps(report,indent=2),flush=True)


def evaluate(oracle,path,resolution=.0004,stop_collision=True):
    minimum=float('inf');n=0;witness=None
    for i,(a,b) in enumerate(zip(path[:-1],path[1:])):
        for pose in interpolate(np.array(a),np.array(b),resolution):
            distance=oracle.distance(pose);n+=1
            if distance<minimum:minimum=distance;witness=dict(segment=i,pose=pose.tolist(),distance_m=distance)
            if distance<=0 and stop_collision:return dict(collision_found=True,minimum_sampled_gap_m=minimum,samples=n,witness=witness)
    return dict(collision_found=minimum<=0,minimum_sampled_gap_m=minimum,samples=n,witness=witness)


def certify(folder):
    folder=Path(folder);trace=json.loads((folder/'ik_before_geometry.json').read_text());oracle=SolidOracle(folder/'assets')
    poses=[f['ball_pose'] for f in trace['frames']]
    positive=evaluate(oracle,poses,.0001)
    original=evaluate(oracle,trace['seed_path'])
    first=np.array(poses[0]);last=np.array(trace['proposed_path'][-1]);pull=last.copy();pull[3:]=first[3:]
    up=first.copy();up[2]+=.30
    down=first.copy();down[2]-=.30
    controls=dict(original_route=original,straight_pull=evaluate(oracle,[first,pull]),
        straight_lift=evaluate(oracle,[first,up]),straight_lower=evaluate(oracle,[first,down]))
    family=trace['family'];path=np.array(trace['proposed_path'])
    if family=='oblique_gate':
        ablation=path.copy();seed=np.array(trace['seed_path']);ablation[:,1]=seed[:,1]
        controls['remove_lateral_excursion']=evaluate(oracle,ablation)
    elif family=='staggered_gates':
        controls['skip_second_gate_alignment']=evaluate(oracle,np.array([*path[:9],path[-1]]))
    else:
        unturned=path.copy();unturned[:,3:]=np.array(trace['seed_path'])[:,3:]
        controls['advance_without_added_turn']=evaluate(oracle,unturned)
        prerotated=path.copy()
        prerotated[:,3:]=(Rotation.from_euler('z',36,degrees=True)*Rotation.from_quat(np.array(trace['seed_path'])[:,3:])).as_quat()
        controls['rotate_first_then_advance']=evaluate(oracle,np.array([first,*prerotated]))
    lower=positive['minimum_sampled_gap_m']-.0001
    passed=not positive['collision_found'] and lower>=.0005 and all(c['collision_found'] for c in controls.values())
    result=dict(passed=passed,family=family,positive=positive,continuous_clearance_lower_bound_m=lower,
        material_motion_bound_m=.0001,finite_controls=controls,unique_solution_proven=False,
        ik_sha256=sha(folder/'ik_before_geometry.json'),asset_manifest_sha256=sha(folder/'assets/sha256.json'),
        source_fingerprints={n:sha(Path(__file__).with_name(n)) for n in ('family_motion.py','family_geometry.py','inverse_window.py','geometry.py','plan_escape.py')})
    save(folder/'certificate.json',result);print(json.dumps(result,indent=2),flush=True)
    if not passed:raise ValueError('Positive route or family discrimination failed')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['sweep','geometry','certify']);p.add_argument('family',choices=FAMILIES);p.add_argument('--output',type=Path,default=OUTPUT)
    a=p.parse_args();folder=a.output/a.family
    if a.action=='sweep':make_sweep(folder)
    elif a.action=='geometry':geometry(folder)
    else:certify(folder)


if __name__=='__main__':main()
