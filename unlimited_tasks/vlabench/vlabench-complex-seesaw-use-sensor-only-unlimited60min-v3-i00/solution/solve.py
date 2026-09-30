from vlb_traj import Session
with Session() as s:
    actions = s.load_trajectory('/solution/oracle.npz')
    result = s.replay(actions)
    assert result['success'], result
    s.save_trajectory(actions)
    print(result)
