"""Pure validation of a privileged metadata receipt. No privileged/broker calls."""
from datetime import datetime, timezone
import re

from .operator_verification import OperatorBlocked

VERSION='p3-system-attestor-v1'
HOST_KEYS={'dedicated_identity','session_zero','non_admin','exclusive_processes','protected_acl','terminal_pid'}


def validate_receipt(receipt, *, nonce, account_key, run_id, python_pid, current):
    keys={'version','nonce','account_key','run_id','python_pid','started_at','completed_at','host'}
    if (not isinstance(receipt,dict) or set(receipt)!=keys or receipt['version']!=VERSION
            or not re.fullmatch(r'[a-f0-9]{32}',nonce)
            or (receipt['nonce'],receipt['account_key'],receipt['run_id'],receipt['python_pid'])
                !=(nonce,account_key,run_id,python_pid)
            or type(receipt['python_pid']) is not int):
        raise OperatorBlocked('HOST_RECEIPT_BINDING_INVALID')
    try:
        start=datetime.fromisoformat(receipt['started_at'].replace('Z','+00:00'))
        finish=datetime.fromisoformat(receipt['completed_at'].replace('Z','+00:00'))
        if (current.tzinfo is None or start.tzinfo is None or finish.tzinfo is None
                or not 0 <= (current-start).total_seconds() <= 5 or not start<=finish<=current):
            raise ValueError()
    except (ValueError,TypeError):
        raise OperatorBlocked('HOST_RECEIPT_STALE_OR_INVALID') from None
    host=receipt['host']
    if (not isinstance(host,dict) or set(host)!=HOST_KEYS
            or any(type(host[k]) is not bool for k in HOST_KEYS-{'terminal_pid'})
            or type(host['terminal_pid']) is not int or host['terminal_pid']<0):
        raise OperatorBlocked('HOST_RECEIPT_SCHEMA_INVALID')
    return dict(host)


def validate_bootstrap_receipt(receipt, *, phase, **binding):
    if (phase not in {'BOOTSTRAP_PREPARE', 'BOOTSTRAP_READ'} or
            not isinstance(receipt, dict) or receipt.get('version') != 'p3-bootstrap-attestor-v1'
            or receipt.get('phase') != phase):
        raise OperatorBlocked('BOOTSTRAP_RECEIPT_BINDING_INVALID')
    value = dict(receipt)
    value.pop('phase')
    value['version'] = VERSION
    host = validate_receipt(value, **binding)
    if any(host[k] is not True for k in HOST_KEYS - {'terminal_pid'}):
        raise OperatorBlocked('BOOTSTRAP_HOST_ISOLATION_NOT_PROVEN')
    if (phase == 'BOOTSTRAP_PREPARE' and host['terminal_pid'] != 0
            or phase == 'BOOTSTRAP_READ' and host['terminal_pid'] <= 0):
        raise OperatorBlocked('BOOTSTRAP_TERMINAL_STATE_INVALID')
    return host
