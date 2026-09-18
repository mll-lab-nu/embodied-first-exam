"""Geometric goal and measured execution validity, separate from the oracle."""


class StagedLockEvaluator:
    def evaluate(self,task,*,execution_ok=True,grasp_released=True,max_geometry_error=0):
        state=task.state()
        execution_ok=bool(execution_ok and not task.force_limit_triggered)
        max_geometry_error=max(max_geometry_error,task.geometry_error_steps)
        contacts_ok=task.max_contact_penetration<=float(task.cfg.physics.max_penetration)
        cfg=task.cfg.success
        geometry=task.layout.clearance(state['depth'],state['key_deg'],state['disc_deg'],tolerance=.5)
        axis_ok=state['axis_offset']<=float(cfg.max_axis_offset) and state['axis_tilt_deg']<=float(cfg.max_axis_tilt_deg)
        reached=abs(state['depth']-4.) <= float(cfg.depth_tolerance) and axis_ok
        rest=abs(state['linear_speed'])<float(cfg.max_linear_speed) and abs(state['angular_speed'])<float(cfg.max_angular_speed)
        success=bool(reached and not geometry and rest and execution_ok and grasp_released and max_geometry_error==0 and contacts_ok)
        return dict(task_id='staged_lock',success=success,reached_endpoint=reached,at_rest=rest,
                    geometry_errors=geometry,axis_alignment_ok=axis_ok,contacts_ok=contacts_ok,
                    execution_ok=execution_ok,grasp_released=grasp_released,state=state)
