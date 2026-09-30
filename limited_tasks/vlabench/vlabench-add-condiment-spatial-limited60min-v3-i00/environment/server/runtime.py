"""Private accounting wrapper; never change simulator controls or predicates."""
def count_physics(session):
    physics=session._env.physics
    original=physics.step
    counter={'steps':0}
    def step(*args,**kwargs):
        n=int(kwargs.get('nstep',args[0] if args else 1))
        try:
            result=original(*args,**kwargs)
        except Exception as exc:
            # dm_control checks warning flags AFTER the MuJoCo integration call.
            if type(exc).__name__=='PhysicsError': counter['steps']+=n
            raise
        counter['steps']+=n
        return result
    physics.step=step
    return counter
