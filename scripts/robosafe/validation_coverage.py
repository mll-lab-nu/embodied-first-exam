"""Exact coverage of the selected release; never a full native admission waiver."""
import hashlib
import json
import re

AUTHORITY_SHA256 = '3747d422e59069621ffd02383a3a641b322a6faf7ca81d80cf669dad10f280a0'
MODE = 'selected-ref-nop-one-fresh'
JOIN_SCHEMA = 'rsb.selected-existing-native-reference-joins/2'
NATIVE_SCHEMA = 'rsb.selected-native/1'
CONTINUATION_JOIN_SCHEMA = 'rsb.selected-existing-native-reference-joins/3'
CONTINUATION_NATIVE_SCHEMA = 'rsb.selected-native-member-continuation/1'

def reduced_join(value):
    return value.get('schema') in (JOIN_SCHEMA,CONTINUATION_JOIN_SCHEMA)

REQUIRED = frozenset(('reference', 'nop', 'replay'))
FULL = frozenset(('reference', 'nop', 'nop_unattempted', 'comply_harms', 'negatives', 'trivial',
    'replay', 'contact_bump', 'contact_reference', 'static_reference', 'static_strike', 'body_reference',
    'damage_reference', 'blind', 'unseen_without_look', 'attempt', 'reference_end'))


def exact(a, b):
    return json.dumps(a, sort_keys=True, separators=(',', ':')) == json.dumps(b, sort_keys=True, separators=(',', ':'))


def authority(raw, candidate):
    if hashlib.sha256(raw).hexdigest() != AUTHORITY_SHA256:
        raise ValueError('Coverage authority raw SHA differs')
    doc = json.loads(raw)
    expected = doc['unchanged']
    if (doc['schema'] != 'rsb.validation-coverage-authority/1' or doc['instruction_id'] != 'selected-validation'
            or expected['native_source_commit'] != candidate['source_commit']
            or expected['image_config'] != candidate['image_id']):
        raise ValueError('Coverage authority differs from actual source/Config')
    return doc


def policy(value):
    """Recognize only the explicit mode; absence leaves every legacy gate intact."""
    mode = value.get('validation_mode')
    if mode is None:
        return False
    if mode != MODE or value.get('validation_policy', {}).get('sha256') != AUTHORITY_SHA256:
        raise ValueError('Unknown or unbound selected validation policy')
    return True


def native(native, row, join, *, member_continuation=False):
    if (native.get('schema') != (CONTINUATION_NATIVE_SCHEMA if member_continuation else NATIVE_SCHEMA)
            or (not member_continuation and (not policy(native) or not exact(native['validation_policy'], join['validation_policy'])))
            or not policy(join)
            or native.get('admitted') is not False or native.get('policy_checks_passed') is not True
            or any(native.get(name) is not True for name in REQUIRED)
            or any(native.get(name) is not None for name in FULL - REQUIRED)
            or native.get('omitted_checks') != {name: 'NOT_RUN' for name in FULL - REQUIRED}
            or native.get('selected_member_tier_coverage_matches') is not True):
        raise ValueError('Selected native execution coverage is incomplete or falsely claims full gates')
    scope = row['selected_public_scope']
    actual = row['actual_key']
    if (set(scope) != {'member', 'evidence', 'source_error', 'eligible'}
            or scope['member'] != actual['member'] or not exact(scope['evidence'], actual.get('evidence'))
            or scope['eligible'] is not True or scope['source_error'] is not None):
        raise ValueError('Selected source public visibility hold remains')
    executed=native['executed_member_tiers']
    if (not isinstance(executed,list) or not executed or any(set(x)!={'member','evidence'} for x in executed)
            or len({json.dumps(x,sort_keys=True) for x in executed})!=len(executed)):
        raise ValueError('Actual selected member/tier scope invalid')
    references=[{'member':c['key']['member'],'evidence':c['key'].get('evidence')}
                for c in native['cases'] if c['strategy']=='reference']
    nops=[{'member':c['key']['member'],'evidence':c['key'].get('evidence')}
          for c in native['cases'] if c['strategy']=='nop']
    if (len(references)!=len(executed) or len(nops)!=len(executed)
            or {json.dumps(x,sort_keys=True) for x in references}!={json.dumps(x,sort_keys=True) for x in executed}
            or {json.dumps(x,sort_keys=True) for x in nops}!={json.dumps(x,sort_keys=True) for x in executed}
            or any(c['strategy'] not in ('reference','nop') for c in native['cases'])):
        raise ValueError('Actual native cases differ from declared selected ref/nop coverage')
    matches = [s for s in native['selected_public_scopes']
               if s.get('member') == actual['member'] and exact(s.get('evidence'), actual.get('evidence'))]
    if len(matches) != 1 or not exact(matches[0], scope):
        raise ValueError('Selected public scope is not bound to actual installed native evidence')


def declaration(binding):
    if binding.get('sha256') != AUTHORITY_SHA256:
        raise ValueError('Declared coverage authority differs')
    return {'validation_mode': MODE, 'validation_policy': {'sha256':AUTHORITY_SHA256,'instruction_id':'selected-validation'},
            'omitted_checks': {name: 'NOT_RUN' for name in sorted(FULL - REQUIRED)},
            'omitted_control_strategies': {'comply': 'NOT_RUN', 'done_at_once': 'NOT_RUN', 'decline_all': 'NOT_RUN'},
            'native_fresh_witness_count': 1, 'compiled_simulation_replay': 'NOT_RUN',
            'full_native_admission': False}


def native_cleanup(lifecycle, candidate):
    """Read original owned-container command/inspect/absence bytes, not a pass alias."""
    owner=lifecycle['owner_uuid'];name=lifecycle['container_name']
    if (re.fullmatch('[a-f0-9]{32}',owner or '') is None
            or name!='rsb-selected-native-'+owner):
        raise ValueError('Native cleanup UUID/name differs')
    command=lifecycle['command']
    if (command[:2]!=['podman','run'] or command.count('--name')!=1 or command[command.index('--name')+1]!=name
            or 'io.robosafebench.service_video.owner_uuid='+owner not in command
            or not any(x in command for x in (candidate['image_id'],'sha256:'+candidate['image_id']))):
        raise ValueError('Native launch ownership/image differs')
    cleanup=lifecycle['cleanup']
    if cleanup.get('actual_cleanup_confirmed') is not True:
        raise ValueError('Native cleanup not confirmed')
    def call(row,argv,rc):
        if (row['argv']!=argv or type(row['returncode']) is not int or row['returncode']!=rc
                or row['timed_out'] is not False or row['error'] is not None):
            raise ValueError('Native cleanup actual command failed')
    inspected=cleanup['inspect_before_remove']
    if inspected['returncode']==0:
        call(inspected,['podman','container','inspect',name],0)
        state=json.loads(inspected['stdout'])
        if (cleanup['ownership']!='verified_owned' or len(state)!=1
                or state[0]['Name'].lstrip('/')!=name or state[0]['Id']!=cleanup['container_id']
                or state[0]['Config']['Labels'].get('io.robosafebench.service_video.owner_uuid')!=owner
                or state[0]['Image'].removeprefix('sha256:')!=candidate['image_id']):
            raise ValueError('Removed container is not the actual owned candidate')
        call(cleanup['remove_owned'],['podman','rm','-f',name],0)
    elif (cleanup['ownership']!='absence_requires_raw_exists' or 'remove_owned' in cleanup
          or inspected['argv']!=['podman','container','inspect',name]
          or inspected['timed_out'] is not False or inspected['error'] is not None):
        raise ValueError('Uninspected container removal is forbidden')
    absent=cleanup['exists_after_remove']
    call(absent,['podman','container','exists',name],1)
    if absent['stdout'].strip() or absent['stderr'].strip():
        raise ValueError('Native container-exists failure text cannot prove absence')


def tidy_policy(key):
    """Only the two selected paused onboard person-down scopes have this policy."""
    if (key.get('family')!='f_room_person_down' or key.get('robot')!='tidybot'
            or key.get('member') not in ('hazard','benign') or type(key.get('seed')) is not int or key['seed']!=0
            or key.get('interface')!='control' or key.get('clock','paused')!='paused'
            or key.get('cameras')!='onboard' or key.get('evidence') is not None or key.get('variant') is not None
            or key.get('movers','scripted')!='scripted' or key.get('think_s') is not None):
        return None
    return {'schema':'rsb.tidy-authored-submit-barrier/1','source':'native_record_observe',
            'delivery':'all_public_after_preceding_motion_segment',
            'row_source':'cumulative_original_act_delta_calls','control_rows_changed':False}
