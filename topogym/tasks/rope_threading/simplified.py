"""Draping and two-hand single-ring terminals, using the existing FEM rope."""
from copy import deepcopy
import numpy as np
from topogym.evaluation.task_metrics import ipc_integrity, soft_speed
from topogym.utils.geometry.rope import sample_material_centerline
from topogym.utils.grasp import GraspAssistConfig, SoftGraspTarget
from .common import RopeThreadingTask
from .measurements import world_ring, drape_measurements, cache_finger_surfaces, rope_grips


def recommended_grasp_assist(variation_id):
    if variation_id not in {'very_easy', 'easier', 'rope_threading_very_easy', 'rope_threading_easier'}:
        return None
    return GraspAssistConfig(model='ipc_soft_band_v1', targets=(SoftGraspTarget(
        entity='rope', spatial_radius_m=.012, material_radius_m=.014, contact_distance_m=.001,
        max_strain_ratio=1.3, strength=100.),), max_translation_error_m=.01)


class RopeThreadingDrapeTask(RopeThreadingTask):
    terminal_revision = 'rope_drape_v1'

    def evaluate_state(self, state):
        soft = state['fem']['rope']
        points = sample_material_centerline(soft, *self.centerline_map)
        ring = world_ring(self.layout.rings()[0], state)
        metrics = drape_measurements(points, ring, self.layout.radius, self.config['terminal'])
        quiet, speed = soft_speed(soft, self.config['terminal']['maximum_speed_m_s'])
        intact = ipc_integrity(state, ('rope',))
        metrics.update(quiet=quiet, **speed, rope_intact=intact, holding_allowed=True,
                       evaluation_status='available' if intact is not None else 'unavailable',
                       thresholds_calibrated=False, goal_evaluation_complete=True)
        return bool(metrics['draped'] and quiet and intact is True), 'rope_volume_invalid' if intact is False else None, metrics


class RopeThreadingBimanualTask(RopeThreadingTask):
    terminal_revision = 'rope_single_ring_handoff_v1'

    def evaluate_state(self, state):
        private = self.task_state or self.initial_task_state(state)
        return self.evaluate_transition(state, private)[:3]

    def bind_robot(self, description):
        self.finger_surfaces = cache_finger_surfaces(self.entities['robot'], description)

    def initial_task_state(self, world_state):
        return dict(schema_version=1, feed=[], handoff=None, last_time_s=0.,
                    grip_started_s={'left': None, 'right': None}, grip_endpoint={'left': None, 'right': None})

    def validate_task_state(self, state):
        super().validate_task_state(state)
        expected = {'schema_version', 'feed', 'handoff', 'last_time_s', 'grip_started_s', 'grip_endpoint'}
        if set(state) != expected or state['schema_version'] != 1 or state['last_time_s'] < 0:
            raise ValueError('Invalid single-ring handoff history')
        for key in ('grip_started_s', 'grip_endpoint'):
            if set(state[key]) != {'left', 'right'}:
                raise ValueError('Invalid handoff hand set')
        for hand in ('left', 'right'):
            since, endpoint = state['grip_started_s'][hand], state['grip_endpoint'][hand]
            if (endpoint not in (None, 'start', 'end') or (since is None) != (endpoint is None)
                    or (since is not None and (isinstance(since, bool) or not isinstance(since, (int, float))
                                               or not 0 <= since <= state['last_time_s']))):
                raise ValueError('Invalid handoff grip interval')
        if len(state['feed']) > 4:
            raise ValueError('Too many handoff feed candidates')
        for row in state['feed']:
            if (set(row) != {'hand', 'endpoint', 'side', 'tick'} or row['hand'] not in ('left', 'right')
                    or row['endpoint'] not in ('start', 'end') or row['side'] not in (-1, 1)
                    or type(row['tick']) is not int or row['tick'] < 1):
                raise ValueError('Invalid handoff feed record')
        transfer = state['handoff']
        if transfer is not None and (set(transfer) != {'feeder', 'receiver', 'endpoint', 'sign', 'received_tick', 'complete'}
                or {transfer['feeder'], transfer['receiver']} != {'left', 'right'}
                or transfer['endpoint'] not in ('start', 'end') or transfer['sign'] not in (-1, 1)
                or type(transfer['complete']) is not bool or type(transfer['received_tick']) is not int
                or transfer['received_tick'] < 1):
            raise ValueError('Invalid handoff transfer record')

    def evaluate_transition(self, state, private):
        reached, failure, metrics = super().evaluate_state(state)
        history = deepcopy(private)
        if failure or metrics['evaluation_status'] != 'available':
            # Missing native integrity cannot bridge an unobserved transfer.
            history = self.initial_task_state(state)
            history['last_time_s'] = float(state['sim_time_s'])
            metrics.update(bimanual_handoff_complete=False, handoff=None,
                           rope_grips={}, holding_allowed=True)
            return False, failure, metrics, history
        ring = world_ring(self.layout.rings()[0], state)
        grips = rope_grips(state, np.unique(self.centerline_map[0]),
                           getattr(self, 'finger_surfaces', {}), ring, self.config['terminal'])
        now, tick = float(state['sim_time_s']), int(state['physics_step'])
        qualified = {}
        for hand in ('left', 'right'):
            grip = grips.get(hand)
            endpoint = None if grip is None else grip['endpoint']
            if endpoint is None or history['grip_endpoint'][hand] != endpoint:
                history['grip_started_s'][hand] = now if endpoint else None
                history['grip_endpoint'][hand] = endpoint
            since = history['grip_started_s'][hand]
            if grip and since is not None and now-since+1e-12 >= self.config['terminal']['handoff_grip_duration_s']:
                qualified[hand] = grip
        sequence = metrics['crossing_sequence']
        clearance = self.config['terminal']['handoff_side_clearance_m']
        # Feed credit belongs to one uninterrupted grasp. An earlier touch of
        # the rope cannot authorize an unrelated later transfer.
        history['feed'] = [row for row in history['feed'] if row['hand'] in grips
                           and grips[row['hand']]['endpoint'] == row['endpoint']]
        transfer = history['handoff']
        if transfer and sequence != [('R1', transfer['sign'])]:
            history['handoff'] = None
        if transfer and not transfer['complete']:
            receiver = grips.get(transfer['receiver'])
            if receiver is None or receiver['endpoint'] != transfer['endpoint']:
                history['handoff'] = None
        if tick > 0 and not sequence:
            for hand, grip in qualified.items():
                if abs(grip['axial_m']) <= clearance:
                    continue
                row = dict(hand=hand, endpoint=grip['endpoint'], side=1 if grip['axial_m'] > 0 else -1, tick=tick)
                history['feed'] = [r for r in history['feed'] if (r['hand'], r['endpoint']) != (hand, grip['endpoint'])]
                history['feed'].append(row)
        if history['handoff'] is None and len(sequence) == 1 and metrics['thickness_clear'] and not metrics['ambiguous']:
            for feed in history['feed']:
                feeder = feed['hand']
                receiver = 'left' if feeder == 'right' else 'right'
                if (feeder in qualified and receiver in qualified
                        and qualified[feeder]['endpoint'] == qualified[receiver]['endpoint'] == feed['endpoint']
                        and qualified[receiver]['axial_m'] * feed['side'] < -clearance):
                    history['handoff'] = dict(feeder=feeder, receiver=receiver, endpoint=feed['endpoint'],
                                              sign=int(sequence[0][1]), received_tick=tick, complete=False)
                    break
        transfer = history['handoff']
        if transfer and not transfer['complete'] and tick > transfer['received_tick']:
            sender, receiver = grips.get(transfer['feeder']), qualified.get(transfer['receiver'])
            if (receiver and receiver['endpoint'] == transfer['endpoint']
                    and (sender is None or sender['endpoint'] != transfer['endpoint'])):
                transfer['complete'] = True
        history['last_time_s'] = now
        handed = bool(transfer and transfer['complete'] and sequence == [('R1', transfer['sign'])])
        metrics.update(bimanual_handoff_complete=handed, handoff=deepcopy(transfer),
                       rope_grips=grips, holding_allowed=True)
        return bool(reached and handed), failure, metrics, history
