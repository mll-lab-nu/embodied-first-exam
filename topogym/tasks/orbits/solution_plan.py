"""Video/PDF-derived bight routes under physical development, not qualified."""
from pathlib import Path
from .dynamics import Probe


PREFIX = [
    ('settle',None,.5),
    ('pdf_01_lift_ring4',[.102,0,.14],2.),
    ('pdf_01_raise_clear',[.08,0,.35],3.),
    ('pdf_02_over_ball',[-.16,0,.35],3.),
    ('pdf_03_outside',[-.19,0,.20],3.),
    ('pdf_04_below_ring1',[-.142,0,.218],2.),
    ('pdf_04_through_ring1',[-.142,0,.335],2.),
    ('pdf_05_across_ball',[-.095,0,.335],2.),
    ('pdf_06_below_ring1',[-.095,0,.219],2.),
    ('pdf_06_bight_ring2',[-.080,0,.166],2.),
]


def run_prefix(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    probe=Probe(folder/'model.xml',spacing=.0075)
    for name,point,seconds in PREFIX:
        probe.move(name,point,seconds=seconds)
    probe.save(folder)
    return probe


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('folder',type=Path)
    run_prefix(parser.parse_args().folder)
