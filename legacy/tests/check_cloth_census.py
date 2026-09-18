"""Exact tear census on duplicate points, outliers, and a dense cloth."""
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from topogym.supervision.cloth_fold import ClothFoldWatch

def census(nodes):
    watch=object.__new__(ClothFoldWatch)
    watch.rest_spacing=.001
    watch.worst_gap=0.
    watch._census(nodes)
    return watch

rng=np.random.default_rng(41)
nodes=rng.normal(size=(217,3))*.03
nodes[4]=nodes[3]
nodes=np.r_[nodes,[[99.,99.,99.]]]
watch=census(nodes)
keep=nodes[:-1]
d=np.linalg.norm(keep[:,None]-keep[None,:],axis=2)
np.fill_diagonal(d,np.inf)
np.testing.assert_allclose([watch.worst_gap,watch.median_gap],[d.min(axis=1).max(),np.median(d.min(axis=1))],rtol=1e-12)
assert watch.n_far==1
print('PASS exact census agrees with all-pairs reference, including duplicates and outlier',flush=True)
x,y=np.meshgrid(np.arange(250)*.001,np.arange(240)*.001)
watch=census(np.c_[x.ravel(),y.ravel(),np.zeros(x.size)])
np.testing.assert_allclose([watch.worst_gap,watch.median_gap],[.001,.001],atol=1e-12)
print('PASS exact census on 60,000 particles',flush=True)
