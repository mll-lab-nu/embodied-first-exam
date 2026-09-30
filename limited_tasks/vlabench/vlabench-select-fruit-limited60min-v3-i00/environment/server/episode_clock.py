"""Trusted agent clock, distinct from the robot episode and post-agent collection."""
import time
from datetime import datetime,timezone
class AgentClock:
 def init_agent_clock(self):
  self.agent_stopped=False;self.agent_timeout=False;self.agent_stop_elapsed=None;self.agent_stopped_at=None
 def deadline(self):
  if self.active and not self.agent_stopped and not self.agent_timeout and self.elapsed()>=3600:
   self.agent_timeout=True
   if not self.ended:self.finish('timeout')
   else:self.event('agent_timeout')
   self.persist()
 def stop_agent(self):
  self.deadline()
  if not self.agent_stopped:
   self.agent_stop_elapsed=self.elapsed();self.agent_stopped_at=datetime.now(timezone.utc).isoformat()
   self.agent_timeout|=self.active and self.agent_stop_elapsed>=3600
   self.agent_stopped=True
   if not self.ended:self.finish('agent_stopped')
   self.event('agent_stop');self.persist()
  return {'stopped':True}
 def agent_clock_fields(self):
  return dict(agent_seconds=self.agent_stop_elapsed if self.agent_stopped else self.elapsed(),
   episode_seconds=self.end_elapsed if self.ended else self.elapsed(),agent_stopped=self.agent_stopped,
   agent_stopped_at=self.agent_stopped_at,agent_timeout=self.agent_timeout,
   termination_reason='timeout' if self.agent_timeout else self.reason,episode_termination_reason=self.reason)
