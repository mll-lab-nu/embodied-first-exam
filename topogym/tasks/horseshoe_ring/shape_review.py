"""Export an offline, interactive geometric replay and auditable shape report."""
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from .geometry import HorseshoeAssembly, horseshoe_band, band_centerline, generate_assets
from .shape_sampler import load_references
from .shape_variants import OUTPUT


def build_review(output=OUTPUT):
    output=Path(output)
    families=load_references(output/'references')
    rows=[];scenes=[]
    for name,(params,bore,neighborhood) in families.items():
        path=neighborhood.path;cert=neighborhood.certificate
        folder=output/'references'/name
        assembly=HorseshoeAssembly(path['template'],path['scale'])
        generate_assets(folder/'assets',template=path['template'],scale=path['scale'])
        h=path['template']['horseshoe'];band,_=horseshoe_band(h,assembly.unit)
        tip=band_centerline(h,assembly.unit,np.array([np.radians(h['mouth_half_angle_deg'])]))[0,0]
        meshes=[]
        for k,body in enumerate(assembly.bodies):
            center=np.asarray(path['centers'][k]);vertices=[];faces=[]
            if body.convex:
                direction=-1 if k==0 else 1
                shoe_center=abs(body.loops[0].center[0])+h['eye_offset_x']*assembly.unit+tip
                rotation=Rotation.from_euler('z',0 if k==0 else np.pi)
                vertices=(rotation.apply(band.vertices)+[direction*shoe_center,0,0]-center).tolist()
                faces=band.faces.tolist()
            meshes.append(dict(name=body.name,vertices=vertices,faces=faces,
                loops=[dict(points=(loop.points()-center).tolist(),radius=loop.wire_radius) for loop in body.loops]))
        frames=[[[*f[n]['pos'],*f[n]['quat']] for n in neighborhood.names] for f in path['frames']]
        scenes.append(dict(id=name,meshes=meshes,frames=np.round(frames,9).tolist(),fold=path['fold_end_index']))
        rows.append(dict(id=name,shape=float(params[0]),ellipse_aspect=float(params[1]),chain_semimajor_mm=float(params[2]),
            bore_margin_mm=bore,frames=len(frames),clearance_mm=cert['minimum_clearance_lower_bound_m']*1000,
            goal_gap_mm=cert['goal']['separation_m']*1000,template_sha256=cert['template_sha256'],frames_sha256=cert['frames_sha256']))
    report=dict(references=rows,scope='Continuous independent-body geometric solutions; robot IK and physical execution are not yet qualified for these shapes',
        rule='Joint parameter perturbations must fit all ten pairwise geometric clearance budgets',
        proposal_limits_are_not_certified_ranges=True)
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (output/'review_data.js').write_text('window.SHAPE_REVIEW='+json.dumps(dict(report=report,scenes=scenes),separators=(',',':'))+';\n')
    template=Path(__file__).with_name('shape_viewer.html').read_text()
    (output/'index.html').write_text(template)
    plot_outlines(output,families)
    return report


def plot_outlines(output,families):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from .shape_variants import seed
    fig,axes=plt.subplots(1,3,figsize=(14,4.6),layout='constrained')
    templates={'original':seed()['template']}
    templates.update({n:v[2].path['template'] for n,v in families.items() if '_chain' not in n})
    for name,t in templates.items():
        h=t['horseshoe'];alpha=np.radians(h['mouth_half_angle_deg'])
        points=band_centerline(h,1.,np.linspace(alpha,2*np.pi-alpha,401))
        axes[0].plot(points[:,0],points[:,1],label=name)
        radii=t['target_ring'].get('centerline_radii',[t['target_ring']['centerline_radius']]*2)
        theta=np.linspace(0,2*np.pi,200)
        axes[1].plot(radii[0]*np.cos(theta),radii[1]*np.sin(theta),label=name)
    for length in sorted({float(v[0][2]) for v in families.values()}):
        theta=np.linspace(0,2*np.pi,200)
        axes[2].plot(length*np.cos(theta),5*np.sin(theta),label=f'L = {length:g} mm')
    for ax,title in zip(axes,['Shoe centerline (fixed terminal anchors)','Target ellipse centerline','One chain link per span']):
        ax.set_aspect('equal');ax.grid(alpha=.2);ax.set_title(title);ax.set_xlabel('Template mm (scene scale = 2)');ax.legend(fontsize=8)
    fig.savefig(output/'shape_comparison.svg');fig.savefig(output/'shape_comparison.png',dpi=160);plt.close(fig)


if __name__=='__main__':
    build_review()
