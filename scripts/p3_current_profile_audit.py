"""Operator-only --audit: fixed-account read connection, never an order or unlock."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))


def startup_confirmation():
    from core.rebuild.operator_verification import OperatorBlocked
    print('AWAITING_STARTUP_CANCEL: Cancel the initial Login dialog only. '
          'After cancellation, confirm with CANCELLED. No native SDK connection has started.', flush=True)
    if sys.stdin.readline().strip() != 'CANCELLED':
        raise OperatorBlocked('CURRENT_PROFILE_STARTUP_CANCEL_NOT_CONFIRMED')


def manual_demo_confirmation():
    from core.rebuild.operator_verification import OperatorBlocked
    print('AWAITING_MANUAL_DEMO_LOGIN: Sign in yourself using ONLY the designated '
          'project DEMO account/server. Do not enter credentials here, open another '
          'terminal, switch accounts afterward or place an order. Confirm with '
          'DEMO_LOGIN_COMPLETED. No native SDK connection has started.', flush=True)
    if sys.stdin.readline().strip() != 'DEMO_LOGIN_COMPLETED':
        raise OperatorBlocked('CURRENT_PROFILE_MANUAL_DEMO_LOGIN_NOT_CONFIRMED')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', action='store_true')
    wait = parser.add_mutually_exclusive_group()
    wait.add_argument('--wait-for-startup-cancel', action='store_true')
    wait.add_argument('--wait-for-manual-demo-login', action='store_true')
    args = parser.parse_args()
    if (args.wait_for_startup_cancel or args.wait_for_manual_demo_login) and not args.audit:
        parser.error('startup confirmation requires --audit')
    if not args.audit:
        report = dict(status='PLAN_ONLY', broker_connected=False, broker_actions=0,
                      broker_execution='HARD_DISABLED', live='LOCKED')
    else:
        try:
            from core.rebuild.current_profile import readonly_audit
            if args.wait_for_manual_demo_login:
                report = readonly_audit(startup_ready=manual_demo_confirmation,
                                        startup_kind='MANUAL_DEMO_LOGIN')
            else:
                report = readonly_audit(startup_ready=startup_confirmation if args.wait_for_startup_cancel else None)
        except Exception as error:
            import re
            from core.rebuild.operator_verification import OperatorBlocked
            code = str(error) if isinstance(error, OperatorBlocked) else 'CURRENT_PROFILE_PRECONNECTION_GATE_FAILED'
            if not re.fullmatch(r'[A-Z0-9_]+', code):
                code = 'CURRENT_PROFILE_PRECONNECTION_GATE_FAILED'
            report = dict(status='NOT_QUALIFIED', blocker=code,
                          broker_actions=0, broker_execution='HARD_DISABLED', live='LOCKED')
    print(json.dumps(report, sort_keys=True))
    return 0 if report['status'] in {'PLAN_ONLY', 'READONLY_AUDIT_COMPLETE'} else 2


if __name__ == '__main__':
    raise SystemExit(main())
