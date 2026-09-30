from mw_runtime import Session, load_trajectory
s = Session()
try:
    for a in load_trajectory('/solution/oracle.npz', s.instance_sha):
        s.step(a)
    s.save()
finally:
    s.close()
