"""Credential-free diagnostic only. No CLI native connection or execution unlock."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from core.rebuild.operator_verification import preflight


def main():
    print(json.dumps(preflight(), sort_keys=True))
    return 2  # Operational gate unmet, not a successful demo verification.


if __name__ == '__main__':
    raise SystemExit(main())
