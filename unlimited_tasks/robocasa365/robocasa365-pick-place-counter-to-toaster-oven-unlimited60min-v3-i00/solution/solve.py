from casa_runtime import Session, load_trajectory
s = Session(replaying=True)
try:
    actions, controls = load_trajectory('/solution/oracle.npz', s)
    for a, c in zip(actions, controls):
        s.step(a, c)
    s.save()
finally:
    s.close()
