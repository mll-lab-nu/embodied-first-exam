from control_public.client import Client
from control_public.anycar_drift_feedback import DEFAULT
c = Client()
c.describe()
for i in range(3):
    r = c.deploy(DEFAULT, 'Frozen nominal controller; repeated for lifecycle validation only, transfer success is not established.')
c.seal(r['round_id'], 'Unadapted nominal baseline; robust randomized success is not established.')
