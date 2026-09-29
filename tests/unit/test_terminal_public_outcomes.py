from topogym.tasks.base import TaskDefinition
from topogym.simulator.interaction import public_info


class EvidenceTask(TaskDefinition):
    defaults={'stable_duration_s':.1}
    def evaluate_state(self,state):
        return state.get('goal',False),state.get('failure'),{'evaluation_status':state.get('status','available')}


def test_missing_evidence_interrupts_stability_and_cannot_report_success():
    task=EvidenceTask(); task.initialize({'physics_step':0})
    task.update({'physics_step':1,'goal':True},.1)
    result=task.update({'physics_step':2,'goal':True,'status':'unavailable'},.1)
    assert result.evaluation_status=='unavailable' and not result.terminated
    assert task.stable_time_s==0
    assert not task.update({'physics_step':3,'goal':True},.1).terminated
    assert task.update({'physics_step':4,'goal':True},.1).task_success


def test_incomplete_success_rule_preserves_known_failure_and_checkpoint():
    task=EvidenceTask(); task.goal_complete=False; task.initialize({'physics_step':0})
    result=task.update({'physics_step':1,'failure':'wire_touched','status':'unavailable'},.01)
    assert result.terminated and result.evaluation_status=='available' and not result.task_success
    saved=task.get_state(); task.set_state(saved)
    assert task.update({'physics_step':2},.01)==result
    info=public_info(dict(goal_evaluation_complete=False,evaluation_status=result.evaluation_status,
        task_terminated=True,task_success=False,failure_code='wire_touched',
        terminal_revision='terminal_v2',termination_reason='private xyz'))
    assert info['task_outcome']=='failure' and info['task_success'] is False
    assert info['failure_code']=='wire_touched' and 'private' not in str(info)


def test_unavailable_does_not_mean_failure():
    info=public_info(dict(goal_evaluation_complete=True,evaluation_status='unavailable',
        task_terminated=False,task_success=False))
    assert info['task_outcome']=='unknown' and info['task_success'] is None
